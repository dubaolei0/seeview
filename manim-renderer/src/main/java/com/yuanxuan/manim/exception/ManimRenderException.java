package com.yuanxuan.manim.exception;

/**
 * 调用 manim 渲染微服务时的异常（连接失败、超时、下载失败、JSON 解析失败等）。
 * 注意：渲染逻辑失败（如 manim 报错）不抛异常，而是返回 success=false 的 {@link RenderResult}。
 */
public class ManimRenderException extends RuntimeException {

    public ManimRenderException(String message) {
        super(message);
    }

    public ManimRenderException(String message, Throwable cause) {
        super(message, cause);
    }
}
