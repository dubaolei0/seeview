const fs = require('fs');
const readline = require('readline');

const targetIds = [
    'q_6019c4d104',
    'q_b6356e3740',
    'q_60e90c39db',
    'q_ede6fc25a2',
    'q_d43f3249d7',
    'q_ee0eb85d34',
    'q_a287a92a0e',
    'q_ad98d26cc3',
];

const targetSet = new Set(targetIds);
const found = {};

const filePath = 'Z:/_共享文件夹/knowledge/高考题目/题库/master_database.jsonl';

const rl = readline.createInterface({
    input: fs.createReadStream(filePath, { encoding: 'utf-8' }),
    crlfDelay: Infinity
});

rl.on('line', (line) => {
    line = line.trim();
    if (!line) return;
    try {
        const obj = JSON.parse(line);
        const qid = obj.id || '';
        if (targetSet.has(qid)) {
            found[qid] = obj;
        }
    } catch (e) {
        // skip bad lines
    }
});

rl.on('close', () => {
    targetIds.forEach((qid, i) => {
        const num = i + 1;
        if (found[qid]) {
            console.log(`=== QUESTION ${num} ===`);
            console.log(JSON.stringify(found[qid], null, 2));
            console.log();
        } else {
            console.log(`=== QUESTION ${num} === NOT FOUND (id=${qid})`);
            console.log();
        }
    });
    console.log(`Total found: ${Object.keys(found).length}/${targetIds.length}`);
});
