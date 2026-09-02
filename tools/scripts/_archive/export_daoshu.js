const fs = require('fs');

const dbPath = './knowledge/高考题目/题库/master_database.jsonl';
const lines = fs.readFileSync(dbPath, 'utf8').trim().split('\n');

const derivativeQuestions = [];

for (const line of lines) {
    if (!line.trim()) continue;
    const obj = JSON.parse(line);

    // Check if it's a derivative-related question
    const kp = obj.knowledge_points || [];
    const ch = obj.knowledge_chapter || '';
    const hasDaoshu = kp.some(k => k.includes('导数')) || ch.includes('导数');

    // Only extract original questions (depth_level=0) and also molecular/atomic that have 导数 tag
    if (hasDaoshu) {
        derivativeQuestions.push(obj);
    }
}

// Sort by source_year, source_exam, source_question_no
derivativeQuestions.sort((a, b) => {
    if (a.source_year !== b.source_year) return a.source_year - b.source_year;
    const aExam = a.source_exam || '';
    const bExam = b.source_exam || '';
    if (aExam !== bExam) return aExam.localeCompare(bExam, 'zh');
    return (a.source_question_no || 0) - (b.source_question_no || 0);
});

// Generate LaTeX output
let latex = '';
latex += '\\documentclass[12pt,a4paper]{article}\n';
latex += '\\usepackage[utf8]{inputenc}\n';
latex += '\\usepackage[T1]{fontenc}\n';
latex += '\\usepackage{amsmath,amssymb,amsfonts}\n';
latex += '\\usepackage{ctex}\n';
latex += '\\usepackage{geometry}\n';
latex += '\\geometry{margin=2cm}\n';
latex += '\\usepackage{hyperref}\n';
latex += '\\usepackage{xcolor}\n';
latex += '\\title{高考导数题汇编（知识库导出）}\n';
latex += '\\author{数学组知识库}\n';
latex += '\\date{\\today}\n';
latex += '\\begin{document}\n';
latex += '\\maketitle\n';
latex += '\\tableofcontents\n';
latex += '\\newpage\n';

let currentYear = '';
let currentExam = '';
let qNum = 0;

for (const q of derivativeQuestions) {
    if (q.depth_level !== 0) continue; // only original questions

    const year = q.source_year || '未知';
    const exam = q.source_exam || '未知';
    const qNo = q.source_question_no || '?';
    const content = (q.content || '').replace(/\*\*/g, '').replace(/\\\*\*/g, '');
    const options = q.options || [];
    const answer = (q.answer || '').replace(/\*\*/g, '');
    const analysis = q.analysis || '';
    const kpts = q.knowledge_points || [];
    const format = q.question_format || '';

    if (year !== currentYear) {
        currentYear = year;
        latex += `\\section{${year}年}\n`;
        currentExam = '';
    }
    if (exam !== currentExam) {
        currentExam = exam;
        latex += `\\subsection{${exam}}\n`;
    }

    qNum++;

    // Question type label
    let typeLabel = '';
    if (format === 'single_choice') typeLabel = '【单选题】';
    else if (format === 'multi_choice') typeLabel = '【多选题】';
    else if (format === 'fill_in_blank') typeLabel = '【填空题】';
    else if (format === 'essay' || format === 'proof' || format === 'solution') typeLabel = '【解答题】';
    else typeLabel = `【${format}】`;

    latex += `\\subsubsection*{第${qNo}题 ${typeLabel}}\n`;
    latex += `\\noindent ${content}\n\n`;

    if (options.length > 0) {
        latex += '\\begin{enumerate}[(A)]\n';
        for (const opt of options) {
            latex += `\\item ${opt}\n`;
        }
        latex += '\\end{enumerate}\n\n';
    }

    latex += `\\noindent \\textbf{答案：}${answer}\n\n`;
    latex += `\\noindent \\textbf{考点：}${kpts.join('、')}\n\n`;

    // Clean markdown from analysis - remove **, *, __
    const cleanAnalysis = analysis.replace(/\*\*/g, '').replace(/__/g, '').replace(/\\\*/g, '');
    const shortAnalysis = cleanAnalysis.length > 800 ? cleanAnalysis.substring(0, 800) + '...' : cleanAnalysis;
    latex += `\\noindent \\textbf{解析：}${shortAnalysis}\n`;
    latex += '\\vspace{0.5cm}\n';
    latex += '\\hrulefill\n\n';
}

latex += `\\end{document}\n`;

// Write output
const outPath = './knowledge/高考题目/题库/导数题汇编_导出.tex';
fs.writeFileSync(outPath, latex, 'utf8');

console.log(`总共导出 ${qNum} 道导数原题（depth_level=0）`);
console.log(`输出文件: ${outPath}`);
