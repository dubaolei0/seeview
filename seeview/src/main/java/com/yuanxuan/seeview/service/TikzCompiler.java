package com.yuanxuan.seeview.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * TikZ 代码 -> PNG 编译器（图库渲染与生题配图共用管线）。
 *
 * <p>调用 {@code python latex_snippet_tool.py --file <tmp.tex> --out <dst.png>}：
 * xelatex 编译并裁剪透明背景。子进程模式沿用讲题服务约定：
 * PYTHONIOENCODING=utf-8 防乱码、redirectErrorStream + 输出重定向到日志文件防管道死锁。
 */
@Component
public class TikzCompiler {

    private static final Logger log = LoggerFactory.getLogger(TikzCompiler.class);

    /** TikZ 配图编译用 python（lecture_pipeline venv，带 pdf2image/PIL/numpy） */
    @Value("${question.tikz-python:${user.dir}/lecture_pipeline/.venv/Scripts/python.exe}")
    private String tikzPython;

    /** TikZ -> PNG 编译脚本（xelatex 编译并裁剪透明背景） */
    @Value("${question.tikz-script:${user.dir}/tools/题目png生成工具/latex_snippet_tool.py}")
    private String tikzScript;

    /** 输出目录（与题目插图同目录，前端经 local-image 渲染） */
    @Value("${question.image-dir:${user.dir}/question_output/images}")
    private String outputDir;

    /** 编译时给 TikZ 的安全大画布宽度，避免大图在页面边界被裁掉。 */
    private static final int RENDER_WIDTH_CM = 100;

    /** 时间戳前缀计数（防多实例/多次运行撞名） */
    private static final AtomicInteger SEQ = new AtomicInteger();

    /**
     * 编译 TikZ 源码为 PNG。
     *
     * @param code TikZ 源码（需含 \begin{tikzpicture}）
     * @return 成功带生成的 PNG 路径；失败带错误摘要（不含路径）
     */
    public Result compile(String code) {
        Path script = Path.of(tikzScript);
        if (!Files.isRegularFile(script)) {
            log.warn("TikZ 渲染脚本不存在: {}", script);
            return new Result(null, "渲染脚本不存在: " + script);
        }
        Path logFile = null;
        try {
            Path dir = Path.of(outputDir);
            Files.createDirectories(dir);
            Path dst = dir.resolve("tikz" + System.currentTimeMillis() + "_" + SEQ.incrementAndGet() + ".png");
            Path tex = Files.createTempFile("tikz_", ".tex");
            logFile = Files.createTempFile("tikz_", ".log");
            Files.writeString(tex, code, StandardCharsets.UTF_8);
            ProcessBuilder pb = new ProcessBuilder(Path.of(tikzPython).toString(), script.toString(),
                            "--file", tex.toString(), "--width", String.valueOf(RENDER_WIDTH_CM), "--crop-x", "--out", dst.toString())
                    .redirectErrorStream(true)
                    .redirectOutput(logFile.toFile());
            pb.environment().put("PYTHONIOENCODING", "utf-8");
            Process p = pb.start();
            // 工具内部 xelatex 上限 120s（MiKTeX 后台装包时会慢），外层超时留足余量
            if (!p.waitFor(200, TimeUnit.SECONDS)) {
                p.destroyForcibly();
                log.warn("TikZ 编译超时（>200s）");
                return new Result(null, "编译超时（>200s），请检查 TikZ 代码是否过于复杂");
            }
            if (p.exitValue() != 0 || !Files.isRegularFile(dst)) {
                String out = Files.readString(logFile, StandardCharsets.UTF_8);
                log.warn("TikZ 编译失败:\n{}", out);
                return new Result(null, "XeLaTeX 编译失败，请检查 TikZ 代码（括号配对/命令拼写）" + errorTail(out));
            }
            log.info("TikZ 配图已生成: {}", dst);
            return new Result(dst, null);
        } catch (Exception e) {
            log.warn("TikZ 编译异常: {}", e.getMessage());
            return new Result(null, "编译异常: " + e.getMessage());
        } finally {
            if (logFile != null) {
                try {
                    Files.deleteIfExists(logFile);
                } catch (IOException ignored) {
                }
            }
        }
    }

    /**
     * 编译错误摘要：优先取 "!" 开头的 TeX 报错行（附其下一行上下文），没有则取日志末尾几行。
     * 带 "：" 前缀拼在概要后，给前端提示与修正模型看；摘要为空返回空串。
     */
    private static String errorTail(String log) {
        if (log == null || log.isBlank()) return "";
        StringBuilder sb = new StringBuilder();
        String[] lines = log.split("\\r?\\n");
        for (int i = 0; i < lines.length && sb.length() < 600; i++) {
            String l = lines[i].stripTrailing();
            if (l.startsWith("!")) {
                sb.append('\n').append(l);
                if (i + 1 < lines.length && !lines[i + 1].isBlank() && !lines[i + 1].startsWith("!")) {
                    sb.append('\n').append(lines[i + 1].stripTrailing());
                }
            }
        }
        if (sb.isEmpty()) {
            for (int i = lines.length - 1; i >= 0 && sb.length() < 300; i--) {
                if (!lines[i].isBlank()) sb.insert(0, '\n' + lines[i].stripTrailing());
            }
        }
        return sb.isEmpty() ? "" : "：" + sb;
    }

    /** 编译结果：成功带生成的 PNG 路径，失败带错误摘要 */
    public record Result(Path path, String error) {
        public boolean ok() {
            return path != null;
        }
    }
}
