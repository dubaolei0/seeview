package com.yuanxuan.seeview.dto;

import java.util.List;

/**
 * AI 修改题干（智能命题工作台）请求：当前题干 + 选项/答案参考 + 对话历史交给大模型改写。
 *
 * @param stem     当前题干（Markdown 源文本，可含公式、图片链接与 tikz 代码块），必需
 * @param options  该题选项（客观题），可选，供模型保持题干与选项一致
 * @param answer   该题答案，可选，供模型提醒答案是否需同步调整
 * @param note     该题解析，可选
 * @param messages 对话历史（{role: user|assistant, content}，最新在后），
 *                 assistant 内容为此前每轮的修改说明；最新一条 user 即本次修改要求，必需
 */
public record StemFixRequest(
        String stem,
        List<String> options,
        String answer,
        String note,
        List<Message> messages
) {

    /** 一轮对话：role 为 user 或 assistant */
    public record Message(String role, String content) implements ChatTurn {
    }
}
