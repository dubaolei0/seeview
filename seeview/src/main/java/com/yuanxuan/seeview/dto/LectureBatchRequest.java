package com.yuanxuan.seeview.dto;

import java.util.List;

/**
 * 多题批量生成请求。上传一份含多道题的文档（如 选题 .md），后端按 {@code ---} 分段后并发生成。
 *
 * @param document        多题原文（必填）；题与题之间用单独一行 {@code ---} 分隔，每题含 {@code 【题干】}
 * @param problemIdPrefix 题目 id 前缀，缺省 {@code problem_时间戳}；每题 id 为 {@code 前缀_01}、{@code 前缀_02}…
 * @param budget          简洁 | 标准，缺省「标准」；「简洁」只生成 yaml（fast 模式，无备课/讲稿）
 * @param outputDir       输出目录，缺省取配置 lecture.output-dir
 * @param memberName      成员姓名，可选
 * @param concurrency     并发度，缺省取配置 lecture.batch-concurrency（默认 3）
 * @param extraInstructions 用户补充提示词，可选；应用到每道题，注入备课、讲稿与简洁（fast）模式 yaml
 * @param bannedWords     禁用词清单，可选；应用到每道题，命中自动修正一轮
 */
public record LectureBatchRequest(
        String document,
        String problemIdPrefix,
        String budget,
        String outputDir,
        String memberName,
        Integer concurrency,
        String extraInstructions,
        List<String> bannedWords
) {
}
