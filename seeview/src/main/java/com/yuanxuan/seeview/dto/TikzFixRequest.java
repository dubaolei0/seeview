package com.yuanxuan.seeview.dto;

import java.util.List;

/**
 * AI 修正配图（智能命题工作台）请求：题干 + 当前 TikZ 源码 + 对话历史交给大模型修正。
 *
 * @param stem    配图所属题目的题干（前端已剥离图片链接与 TikZ 代码块），可选但建议提供
 * @param code    当前 TikZ 源码，必需
 * @param messages 对话历史（{role: user|assistant, content}，最新在后），
 *                 assistant 内容为此前每轮的修改说明；最新一条 user 即本次修改要求，必需
 */
public record TikzFixRequest(
        String stem,
        String code,
        List<Message> messages
) {

    /** 一轮对话：role 为 user 或 assistant */
    public record Message(String role, String content) implements ChatTurn {
    }
}
