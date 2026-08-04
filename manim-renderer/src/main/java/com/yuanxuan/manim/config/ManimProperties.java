package com.yuanxuan.manim.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;

import java.time.Duration;

/**
 * manim 渲染客户端配置。
 *
 * 对应 application.yml：
 * <pre>
 * manim:
 *   base-url: http://localhost:8000
 *   timeout: 300s
 *   connect-timeout: 10s
 * </pre>
 */
@Data
@ConfigurationProperties(prefix = "manim")
public class ManimProperties {

    /** Python 渲染微服务地址（HTTP 客户端模式，本方案不走此路） */
    private String baseUrl = "http://localhost:8000";

    /** Python 解释器路径（lecture_pipeline 的 venv），用于子进程渲染 */
    private String python = "lecture_pipeline/.venv/Scripts/python.exe";

    /** lecture_pipeline 引擎目录（含 renderer/、src/ 等），子进程 cwd */
    private String engineDir = "lecture_pipeline";

    /** 阿里云 CosyVoice TTS key，通过环境变量 DASHSCOPE_API_KEY 传给 python 子进程 */
    private String dashscopeKey;

    /** 单次渲染读超时（含渲染耗时），默认 600s */
    private Duration timeout = Duration.ofSeconds(600);

    /** 连接超时，默认 10s */
    private Duration connectTimeout = Duration.ofSeconds(10);
}
