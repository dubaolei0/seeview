package com.yuanxuan.seeview.dto;

/**
 * 讲题视频三段式生成请求。
 *
 * @param problem    题目原文（LaTeX 或纯文本），必需
 * @param problemId  题目 id，缺省按时间戳生成，决定输出文件名前缀
 * @param answerHint 题面标注答案，可选
 * @param budget     简洁 | 标准，缺省「标准」；「简洁」只生成 yaml（fast 模式，无备课/讲稿）
 * @param outputDir  输出目录，缺省取配置 lecture.output-dir
 * @param memberName 成员姓名，可选；指定且能读到 profile.md 时注入「讲题视频偏好」
 */
public record LectureRequest(
        String problem,
        String problemId,
        String answerHint,
        String budget,
        String outputDir,
        String memberName
) {
}
