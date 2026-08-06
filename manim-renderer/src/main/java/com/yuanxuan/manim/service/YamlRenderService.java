package com.yuanxuan.manim.service;

import com.yuanxuan.manim.config.ManimProperties;
import com.yuanxuan.manim.enums.Quality;
import com.yuanxuan.manim.exception.ManimRenderException;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.stream.Stream;

/**
 * 子进程渲染 Service：调用本地 lecture_pipeline 引擎（Python + Manim + TTS），
 * 把 maths 讲题 yaml 渲染成带配音 mp4。
 *
 * <p>方式类似 maths 的 render.py：
 * {@code python -m renderer.render <yaml> --quality <low|medium|high> --tts-voice <voice>}，
 * 音频驱动渲染（TTS 先行定时间轴，Manim 画面同步）。
 *
 * <p>yaml 解析与 schema 校验由 python 引擎负责（{@code LectureDoc.from_yaml_file} + {@code validate}），
 * 本类只透传 yaml、编排子进程、回读 mp4。
 *
 * 用法（宿主应用 @Autowired 后）：
 * <pre>
 * byte[] mp4 = yamlRenderService.renderYaml(yamlText, Quality.MEDIUM, "longwan");
 * </pre>
 */
public class YamlRenderService {

    private final ManimProperties props;

    public YamlRenderService(ManimProperties props) {
        this.props = props;
    }

    /**
     * 渲染 yaml 为 mp4，返回视频字节。
     *
     * @param yaml    maths v3 讲稿 yaml 文本
     * @param quality 画质（仅 LOW/MEDIUM/HIGH；PRODUCTION/FOUR_K 不支持，renderer.render 限制）
     * @param voice   可选 TTS 音色短名或 ID（如 longwan / liufei / zh_...）；null 用服务端默认
     * @return mp4 字节
     * @throws IOException          读写临时文件失败
     * @throws ManimRenderException 渲染失败、超时或环境缺失
     */
    public byte[] renderYaml(String yaml, Quality quality, String voice) throws IOException {
        return renderYaml(yaml, quality, voice, null);
    }

    /**
     * 渲染 yaml 为 mp4，返回视频字节；可选把 mp4 落盘到 {@code saveTo}（如 yaml 同目录）。
     *
     * @param saveTo 可选 mp4 保存路径；null 仅返回字节不落盘。落盘文件不参与临时清理。
     */
    public byte[] renderYaml(String yaml, Quality quality, String voice, Path saveTo) throws IOException {
        mapQuality(quality);  // 提前校验画质（PRODUCTION/FOUR_K 不支持，抛错）

        Path engineDir = Path.of(props.getEngineDir()).toAbsolutePath().normalize();
        if (!Files.isDirectory(engineDir)) {
            throw new ManimRenderException("引擎目录不存在: " + engineDir);
        }
        Path pythonPath = resolvePython(engineDir);
        if (!Files.isExecutable(pythonPath)) {
            throw new ManimRenderException("python 解释器不可用: " + pythonPath
                    + "（请在 lecture_pipeline 下建 venv: python -m venv .venv"
                    + " && .venv\\Scripts\\pip install -r requirements.txt）");
        }

        // 1. 写临时 yaml（problem_id = 文件名 stem，renderer 用它命名输出 mp4）
        String problemId = "see_" + UUID.randomUUID().toString().replace("-", "").substring(0, 16);
        Path yamlFile = engineDir.resolve(problemId + ".yaml");
        Files.writeString(yamlFile, yaml, StandardCharsets.UTF_8);

        // 隔离 media 目录：并发渲染时各进程独立，避免 partial_movie_files / Tex 缓存互相覆盖
        Path mediaDir = engineDir.resolve("media_runs").resolve(problemId);
        Files.createDirectories(mediaDir);

        Path logFile = engineDir.resolve(problemId + ".log");
        Path mp4File = null;
        try {
            // 2. 构造命令：python -m renderer.render <yaml> --quality <q> [--tts-voice <v>] [--media-dir <d>]
            List<String> cmd = buildCommand(pythonPath.toString(),
                    yamlFile.toAbsolutePath().toString(), quality, voice, mediaDir.toAbsolutePath().toString());

            // 3. 跑进程：cwd=engineDir，输出重定向到文件避免管道死锁
            ProcessBuilder pb = new ProcessBuilder(cmd)
                    .directory(engineDir.toFile())
                    .redirectErrorStream(true)
                    .redirectOutput(logFile.toFile());
            applyEnvironment(pb);

            Process process;
            try {
                process = pb.start();
            } catch (IOException e) {
                throw new ManimRenderException("启动 python 渲染进程失败: " + e.getMessage(), e);
            }

            String output;
            boolean finished;
            try {
                finished = process.waitFor(props.getTimeout().toSeconds(), TimeUnit.SECONDS);
                output = Files.exists(logFile) ? Files.readString(logFile, StandardCharsets.UTF_8) : "";
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new ManimRenderException("渲染被中断", e);
            }
            if (!finished) {
                process.destroyForcibly();
                throw new ManimRenderException("渲染超时（>" + props.getTimeout().toSeconds() + "s）\n" + output);
            }
            if (process.exitValue() != 0) {
                throw new ManimRenderException("渲染失败（exit=" + process.exitValue() + "）\n" + output);
            }

            // 4. 找 mp4
            mp4File = findMp4(mediaDir, problemId);
            if (mp4File == null) {
                throw new ManimRenderException("渲染完成但未找到输出视频 " + problemId + ".mp4\n" + output);
            }
            byte[] mp4 = Files.readAllBytes(mp4File);
            // 4.1 可选：落盘到调用方指定路径（如 yaml 同目录），与临时 media 清理无关
            if (saveTo != null) {
                Path out = saveTo.toAbsolutePath().normalize();
                if (out.getParent() != null) {
                    Files.createDirectories(out.getParent());
                }
                Files.copy(mp4File, out, StandardCopyOption.REPLACE_EXISTING);
            }
            return mp4;
        } finally {
            // 5. 清理临时文件（含隔离的 media 目录）
            Files.deleteIfExists(yamlFile);
            Files.deleteIfExists(logFile);
            if (mp4File != null) {
                try {
                    Files.deleteIfExists(mp4File);
                } catch (IOException ignored) {
                }
            }
            deleteRecursively(mediaDir);
        }
    }

    /** 构造渲染命令：python -m renderer.render <yaml> --quality <q> [--tts-voice <v>]。 */
    List<String> buildCommand(String pythonPath, String yamlAbsPath, Quality quality, String voice) {
        return buildCommand(pythonPath, yamlAbsPath, quality, voice, null);
    }

    /** 同上，额外支持 --media-dir（并发渲染隔离用）。 */
    List<String> buildCommand(String pythonPath, String yamlAbsPath, Quality quality, String voice, String mediaDir) {
        List<String> cmd = new ArrayList<>();
        cmd.add(pythonPath);
        cmd.add("-m");
        cmd.add("renderer.render");
        cmd.add(yamlAbsPath);
        cmd.add("--quality");
        cmd.add(mapQuality(quality));
        if (voice != null && !voice.isBlank()) {
            cmd.add("--tts-voice");
            cmd.add(voice);
        }
        if (mediaDir != null && !mediaDir.isBlank()) {
            cmd.add("--media-dir");
            cmd.add(mediaDir);
        }
        return cmd;
    }

    /** 画质映射：renderer.render 的 --quality 只接受 low/medium/high。 */
    String mapQuality(Quality quality) {
        return switch (quality) {
            case LOW -> "low";
            case MEDIUM -> "medium";
            case HIGH -> "high";
            case PRODUCTION, FOUR_K -> throw new IllegalArgumentException(
                    "本地渲染不支持 " + quality + " 画质，仅支持 LOW/MEDIUM/HIGH");
        };
    }

    /**
     * 把子进程需要的环境变量注入 ProcessBuilder：
     * <ul>
     *   <li>{@code PYTHONIOENCODING=utf-8}：强制 python stdout/stderr 走 utf-8，避免 Windows 控制台 GBK 乱码</li>
     *   <li>{@code DASHSCOPE_API_KEY}：阿里云 CosyVoice TTS key；未配则不注入（python 侧走 .env 或失败）</li>
     * </ul>
     * 抽成独立方法便于单测（无需真起进程）。
     */
    void applyEnvironment(ProcessBuilder pb) {
        pb.environment().put("PYTHONIOENCODING", "utf-8");
        if (props.getDashscopeKey() != null && !props.getDashscopeKey().isBlank()) {
            pb.environment().put("DASHSCOPE_API_KEY", props.getDashscopeKey());
        }
    }

    /** 解析 python 路径：相对路径基于 engineDir。 */
    private Path resolvePython(Path engineDir) {
        Path p = Path.of(props.getPython());
        return p.isAbsolute() ? p : engineDir.resolve(p);
    }

    /** 在 <mediaDir>/videos/** 下找 <problemId>.mp4（manim 按画质分子目录）。 */
    private Path findMp4(Path mediaDir, String problemId) throws IOException {
        Path videosDir = mediaDir.resolve("videos");
        if (!Files.isDirectory(videosDir)) {
            return null;
        }
        String target = problemId + ".mp4";
        try (Stream<Path> walk = Files.walk(videosDir)) {
            return walk.filter(p -> p.getFileName().toString().equals(target))
                    .findFirst().orElse(null);
        }
    }

    /** 递归删除目录（隔离 media 目录清理用，失败忽略）。 */
    private void deleteRecursively(Path dir) {
        if (dir == null || !Files.exists(dir)) {
            return;
        }
        try (Stream<Path> walk = Files.walk(dir)) {
            walk.sorted(Comparator.reverseOrder()).forEach(p -> {
                try {
                    Files.deleteIfExists(p);
                } catch (IOException ignored) {
                }
            });
        } catch (IOException ignored) {
        }
    }

    /**
     * 环境自检：python、engineDir、ffmpeg、xelatex、TTS key 是否就绪。
     * 供启动预检或 /check 接口调用，不在每次渲染中重复执行。
     *
     * @return 缺失项列表；空列表表示环境就绪
     */
    public List<String> checkEnvironment() {
        List<String> problems = new ArrayList<>();
        Path engineDir = Path.of(props.getEngineDir()).toAbsolutePath().normalize();
        if (!Files.isDirectory(engineDir)) {
            problems.add("引擎目录不存在: " + engineDir);
        }
        Path pythonPath = resolvePython(engineDir);
        if (!Files.isExecutable(pythonPath)) {
            problems.add("python 不可用: " + pythonPath
                    + "（建 venv: python -m venv .venv && .venv\\Scripts\\pip install -r requirements.txt）");
        }
        if (!commandExists("ffmpeg")) {
            problems.add("ffmpeg 未在 PATH（渲染合并音视频需要）");
        }
        if (!commandExists("xelatex")) {
            problems.add("xelatex 未在 PATH（LaTeX 公式渲染需要，装 MiKTeX）");
        }
        if (props.getDashscopeKey() == null || props.getDashscopeKey().isBlank()) {
            problems.add("未配 manim.dashscope-key（阿里云 TTS，否则配音失败）");
        }
        return problems;
    }

    private boolean commandExists(String cmd) {
        try {
            Process p = new ProcessBuilder(cmd, "-version").redirectErrorStream(true).start();
            boolean ok = p.waitFor(5, TimeUnit.SECONDS);
            return ok && p.exitValue() == 0;
        } catch (Exception e) {
            return false;
        }
    }
}
