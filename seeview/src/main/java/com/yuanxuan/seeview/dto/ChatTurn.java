package com.yuanxuan.seeview.dto;

/**
 * 对话轮次（AI 修正类接口共用：题干修正、TikZ 配图修正）。
 * role 为 user 或 assistant，content 为消息文本。
 */
public interface ChatTurn {

    String role();

    String content();
}
