package com.yuanxuan.seeview.service;

import com.yuanxuan.manim.config.ManimProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

/**
 * yaml 校验 Service：调用 see 工程自带的 lecture_pipeline Python 引擎，对生成的 yaml 跑三道检查。
 *
 * <p>三道检查（cwd=engineDir，模块名不带 {@code lecture_pipeline.} 前缀，与 {@link
 * com.yuanxuan.manim.service.YamlRenderService} 一致）：
 * <ol>
 *   <li>{@code python -m renderer.render <yaml> --validate-only} —— v3 schema 校验，失败 exit=1</li>
 *   <li>{@code python scripts/check_math_env_cjk.py <yaml>} —— 数学环境禁裸中文，命中 exit=1</li>
 *   <li>{@code python -m normalize_say <yaml>} —— say 个位数汉化（就地改写），多位数残留 exit=1</li>
 * </ol>
 *
 * <p>子进程模式照搬 YamlRenderService：{@code PYTHONIOENCODING=utf-8} 防Windows GBK 乱码、
 * {@code redirectErrorStream + redirectOutput} 到日志文件防管道死锁。
 *
 * <p>本类只做子进程编排与结果汇总；LLM 修正循环由 {@link LectureGenerateService} 负责。
 */
@Service
public class LectureValidateService {

    private static final Logger log = LoggerFactory.getLogger(LectureValidateService.class);

    @Autowired
    private ManimProperties props;

    /**
     * 对一份 yaml 依次跑三道检查。
     *
     * @param yaml yaml 文件绝对路径
     * @return 三道检查的结构化结果；normalize_say 已就地改写该文件
     */
    public CheckReport runChecks(Path yaml) throws IOException, InterruptedException {
        Path engineDir = Path.of(props.getEngineDir()).toAbsolutePath().normalize();
        if (!Files.isDirectory(engineDir)) {
            throw new IOException("引擎目录不存在: " + engineDir);
        }
        Path python = resolvePython(engineDir);
        if (!Files.isExecutable(python)) {
            throw new IOException("python 解释器不可用: " + python);
        }
        String yamlAbs = yaml.toAbsolutePath().toString();

        // 三道检查共用一个临时日志文件（每次 redirect 覆盖）
        Path logFile = engineDir.resolve("validate_" + UUID.randomUUID().toString().replace("-", "").substring(0, 16) + ".log");
        try {
            ProcResult schema = exec(python, engineDir, logFile, "-m", "renderer.render", yamlAbs, "--validate-only");
            ProcResult cjk = exec(python, engineDir, logFile, "scripts/check_math_env_cjk.py", yamlAbs);
            ProcResult norm = exec(python, engineDir, logFile, "-m", "normalize_say", yamlAbs);
            return new CheckReport(schema, cjk, norm);
        } finally {
            try {
                Files.deleteIfExists(logFile);
            } catch (IOException ignored) {
            }
        }
    }

    /**
     * 单条子进程执行。输出重定向到日志文件，waitFor 后回读，避免管道死锁。
     */
    private ProcResult exec(Path python, Path cwd, Path logFile, String... args) throws IOException, InterruptedException {
        List<String> cmd = new ArrayList<>();
        cmd.add(python.toString());
        Collections.addAll(cmd, args);

        ProcessBuilder pb = new ProcessBuilder(cmd)
                .directory(cwd.toFile())
                .redirectErrorStream(true)
                .redirectOutput(logFile.toFile());
        pb.environment().put("PYTHONIOENCODING", "utf-8");

        Process process = pb.start();
        boolean finished = process.waitFor(props.getTimeout().toSeconds(), TimeUnit.SECONDS);
        if (!finished) {
            process.destroyForcibly();
            throw new IOException("校验超时（>" + props.getTimeout().toSeconds() + "s）: " + String.join(" ", args));
        }
        String output = Files.exists(logFile) ? Files.readString(logFile, StandardCharsets.UTF_8) : "";
        log.debug("[validate] {} -> exit={}\n{}", String.join(" ", args), process.exitValue(), output);
        return new ProcResult(process.exitValue(), output);
    }

    private Path resolvePython(Path engineDir) {
        Path p = Path.of(props.getPython());
        return p.isAbsolute() ? p : engineDir.resolve(p);
    }

    /** 单道检查结果。 */
    public record ProcResult(int exitCode, String output) {
        public boolean ok() {
            return exitCode == 0;
        }
    }

    /** 三道检查的汇总。 */
    public record CheckReport(ProcResult schema, ProcResult cjk, ProcResult norm) {

        /** 三道全过。 */
        public boolean allClean() {
            return schema.ok() && cjk.ok() && norm.ok();
        }

        /**
         * 拼接给大模型的修正反馈（仅失败项），用于 LLM 修正循环。
         * normalize_say 的多位数残留属于「需大模型决定读法」的 B 类问题，也一并回传。
         */
        public String feedback() {
            StringBuilder sb = new StringBuilder();
            if (!schema.ok()) {
                sb.append("【schema 校验失败】请按 v3 schema 修正结构/字段错误：\n")
                        .append(truncate(schema.output(), 2000)).append("\n\n");
            }
            if (!cjk.ok()) {
                sb.append("【数学环境裸中文检查命中】$...$ 等数学环境内部不得放裸中文/中文标点，需用 \\text{} 包裹或移到环境外：\n")
                        .append(truncate(cjk.output(), 2000)).append("\n\n");
            }
            if (!norm.ok()) {
                sb.append("【normalize_say 多位数残留】say 字段里的多位数需改成汉字基数读法（如 120->一百二十、第14问->第十四问），脚本不自动转：\n")
                        .append(truncate(norm.output(), 2000)).append("\n\n");
            }
            return sb.toString().trim();
        }

        /** 各道检查的一句话摘要，写进 ValidationReport。 */
        public String schemaSummary() {
            return schema.ok() ? "ok" : "失败(exit=" + schema.exitCode() + ")";
        }

        public String cjkSummary() {
            return cjk.ok() ? "ok" : "命中(exit=" + cjk.exitCode() + ")";
        }

        public String normSummary() {
            return norm.ok() ? "ok" : "多位数残留(exit=" + norm.exitCode() + ")";
        }

        private String truncate(String s, int max) {
            if (s == null) {
                return "";
            }
            return s.length() <= max ? s : s.substring(0, max) + "\n…（已截断）";
        }
    }
}
