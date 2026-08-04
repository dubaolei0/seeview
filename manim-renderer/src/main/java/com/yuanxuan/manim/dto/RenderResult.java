package com.yuanxuan.manim.dto;


import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 渲染微服务返回的结果。
 */
@Data
@NoArgsConstructor
public class RenderResult {

    /** 渲染是否成功；null 视为 false */
    private Boolean success;

    /** 可下载的相对路径，如 /videos/xxx.mp4 */
    private String videoUrl;

    /** 服务端绝对路径（跨进程无意义，仅诊断用） */
    private String videoPath;

    /** 渲染耗时（毫秒） */
    private Long durationMs;

    /** 失败原因 */
    private String error;

    /** manim stderr 片段（失败时可能返回） */
    private String stderr;

    /** 是否渲染成功（success 为 null 时视为失败）。 */
    public boolean isSuccess() {
        return Boolean.TRUE.equals(success);
    }
}
