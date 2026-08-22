package com.yuanxuan.seeview.dto;

import java.util.List;

/**
 * AI 生题（智能命题工作台）生成的题目组。
 *
 * <p>与前端 ai-question.html 约定的结构一致：
 * {@code {title, topic, difficulty, sections:[{type, items:[{q, o?, a, note?, d?}]}],
 * totalQ, source, prompt}}。
 * 大模型只需产出 title/topic/sections，其余字段由后端计算补齐。
 */
public record QuestionPaper(
        String title,
        String topic,
        String difficulty,
        List<Section> sections,
        int totalQ,
        String source,
        String prompt
) {

    /** 大题：题型 + 小题列表 */
    public record Section(String type, List<Item> items) {
    }

    /**
     * 小题。
     *
     * @param q    题干
     * @param o    选项，仅客观题（单选/多选/判断）有
     * @param a    答案；多选题形如 "ABD"，判断题为「正确/错误」
     * @param note 简要解析，可选
     * @param d    难度（容易/中等/较难），可选
     */
    public record Item(String q, List<String> o, String a, String note, String d) {
    }
}
