package com.yuanxuan.seeview.dto;

/**
 * 讲题视频三段式生成结果：三份文档的落盘路径与正文，及 yaml 校验报告。
 *
 * @param problemId    实际使用的题目 id
 * @param beikePath    备课.md 文件路径
 * @param jianggaoPath 讲稿.md 文件路径
 * @param yamlPath     yaml 文件路径
 * @param beike        备课.md 正文
 * @param jianggao     讲稿.md 正文
 * @param yaml         yaml 正文（经 normalize_say 就地改写后的最终版）
 * @param validation   yaml 校验闭环报告
 */
public record LectureResult(
        String problemId,
        String beikePath,
        String jianggaoPath,
        String yamlPath,
        String beike,
        String jianggao,
        String yaml,
        ValidationReport validation
) {
    /**
     * yaml 校验闭环报告。
     *
     * @param enabled 是否启用校验闭环
     * @param passed  最终是否全过（schema + 裸中文 + normalize_say 均 exit 0）
     * @param schema  schema 校验结果摘要（ok / 失败信息）
     * @param cjk     数学环境裸中文检查结果摘要
     * @param normalize normalize_say 结果摘要（ok / 多位数残留）
     * @param rounds  实际执行的 LLM 修正轮数
     * @param notes   备注（如「环境不可用，已跳过」）
     */
    public record ValidationReport(
            boolean enabled,
            boolean passed,
            String schema,
            String cjk,
            String normalize,
            int rounds,
            String notes
    ) {
    }
}
