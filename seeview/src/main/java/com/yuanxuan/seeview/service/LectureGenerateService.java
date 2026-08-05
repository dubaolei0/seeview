package com.yuanxuan.seeview.service;

import com.yuanxuan.manim.config.ManimProperties;
import com.yuanxuan.seeview.dto.LectureBatchRequest;
import com.yuanxuan.seeview.dto.LectureRequest;
import com.yuanxuan.seeview.dto.LectureResult;
import com.yuanxuan.seeview.dto.LectureResult.ValidationReport;
import com.yuanxuan.seeview.service.LectureValidateService.CheckReport;
import dev.langchain4j.data.message.SystemMessage;
import dev.langchain4j.data.message.UserMessage;
import dev.langchain4j.model.chat.request.ChatRequest;
import dev.langchain4j.model.chat.response.ChatResponse;
import dev.langchain4j.model.openai.OpenAiChatModel;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 讲题视频三段式生成 Service。
 *
 * <p>串行三次大模型调用，每次把项目内的规则/样例/schema 注入提示词，依次产出：
 * <ol>
 *   <li>备课.md（system=备课.md 提示词 + 按 budget 选 1 份备课样例）</li>
 *   <li>讲稿.md（system=讲稿.md 提示词 + tts_读法约定 + 讲稿样例 + 备课）</li>
 *   <li>yaml（system=yaml.md 提示词 + tts_读法约定 + schema规范 + yaml样例 + 备课 + 讲稿）</li>
 * </ol>
 *
 * <p>yaml 落盘后进入校验闭环：用 {@link LectureValidateService} 跑 schema/裸中文/normalize_say 三道检查，
 * 未过则把报错回传大模型修 yaml、重新落盘再校验，最多 {@code lecture.max-fix-rounds} 轮。
 */
@Service
public class LectureGenerateService {

    private static final Logger log = LoggerFactory.getLogger(LectureGenerateService.class);

    @Autowired
    private OpenAiChatModel chatModel;

    @Autowired
    private LectureValidateService validateService;

    @Autowired
    private ManimProperties props;

    /** 三份提示词所在目录（备课.md / 讲稿.md / yaml.md） */
    @Value("${lecture.skills-dir:${user.dir}/skills/讲题视频}")
    private String skillsDir;

    /** 三份文档输出目录 */
    @Value("${lecture.output-dir:${user.dir}/lecture_output}")
    private String outputDir;

    /** 成员 profile 根目录（team/{姓名}/profile.md），可选 */
    @Value("${lecture.community-dir:${user.dir}/community}")
    private String communityDir;

    /** 是否启用 yaml 校验闭环 */
    @Value("${lecture.validate:true}")
    private boolean validateEnabled;

    /** yaml 校验闭环最大修正轮数 */
    @Value("${lecture.max-fix-rounds:2}")
    private int maxFixRounds;

    /** 多题批量生成的并发度 */
    @Value("${lecture.batch-concurrency:3}")
    private int batchConcurrency;

    /**
     * 三段式生成主入口。
     *
     * @param req 题目与参数（problem 必填）
     * @return 三份文档路径、正文与校验报告
     */
    public LectureResult generate(LectureRequest req) throws IOException {
        String problemId = blank(req.problemId()) ? "problem_" + System.currentTimeMillis() : req.problemId();
        String budget = blank(req.budget()) ? "标准" : req.budget();
        Path outPath = Paths.get(blank(req.outputDir()) ? outputDir : req.outputDir());
        Files.createDirectories(outPath);
        Path pipelineDir = Path.of(props.getEngineDir()).toAbsolutePath().normalize();

        // 读三份提示词
        String beikePrompt = readSkill("备课.md");
        String jianggaoPrompt = readSkill("讲稿.md");
        String yamlPrompt = readSkill("yaml.md");

        // 读注入引用（缺失则跳过，不阻塞）
        String beikeSample = readResource(pipelineDir.resolve("samples/备课样例"), beikeSampleName(budget));
        String ttsRules = readResource(pipelineDir, "rules/tts_读法约定.md");
        String jianggaoSample = readResource(pipelineDir, "samples/自然语言讲稿/problem_18_讲稿.md");
        String schemaSpec = readResource(pipelineDir, "docs/schema规范.md");
        String yamlSample = readResource(pipelineDir.resolve("samples/yaml样例"), yamlSampleName(budget));
        String profile = blank(req.memberName()) ? null
                : readResource(Paths.get(communityDir), "team/" + req.memberName() + "/profile.md");

        // ① 备课
        String beike = chat(beikePrompt,
                buildBeikeUser(req, problemId, budget, outPath.toString(), beikeSample));
        Path beikePath = outPath.resolve(problemId + "_备课.md");
        Files.writeString(beikePath, beike, StandardCharsets.UTF_8);

        // ② 讲稿
        String jianggao = chat(jianggaoPrompt,
                buildJianggaoUser(problemId, budget, outPath.toString(), ttsRules, jianggaoSample, beike));
        Path jianggaoPath = outPath.resolve(problemId + "_讲稿.md");
        Files.writeString(jianggaoPath, jianggao, StandardCharsets.UTF_8);

        // ③ yaml
        String yaml = chat(yamlPrompt,
                buildYamlUser(problemId, budget, outPath.toString(), ttsRules, schemaSpec, yamlSample,
                        profile, beike, jianggao));
        yaml = stripCodeFence(yaml);
        Path yamlPath = outPath.resolve(problemId + ".yaml");
        Files.writeString(yamlPath, yaml, StandardCharsets.UTF_8);

        // ④ yaml 校验闭环
        ValidationReport report = validateEnabled ? validateLoop(yamlPath, yamlPrompt) : skipped();

        String finalYaml = Files.readString(yamlPath, StandardCharsets.UTF_8); // normalize_say 可能就地改写
        return new LectureResult(problemId,
                beikePath.toString(), jianggaoPath.toString(), yamlPath.toString(),
                beike, jianggao, finalYaml, report);
    }

    // ===================== yaml 校验闭环 =====================

    private ValidationReport validateLoop(Path yamlPath, String yamlPrompt) {
        int rounds = 0;
        try {
            CheckReport cr = validateService.runChecks(yamlPath);
            while (!cr.allClean() && rounds < maxFixRounds) {
                String current = Files.readString(yamlPath, StandardCharsets.UTF_8);
                String fixed = chat(yamlPrompt,
                        buildFixUser(yamlPath.getFileName().toString(), current, cr.feedback()));
                Files.writeString(yamlPath, stripCodeFence(fixed), StandardCharsets.UTF_8);
                rounds++;
                cr = validateService.runChecks(yamlPath);
            }
            boolean passed = cr.allClean();
            return new ValidationReport(true, passed,
                    cr.schemaSummary(), cr.cjkSummary(), cr.normSummary(), rounds,
                    passed ? "通过" : "仍有未通过项（已用尽修正轮数）");
        } catch (Exception e) {
            log.warn("yaml 校验闭环异常，已跳过: {}", e.getMessage(), e);
            return new ValidationReport(true, false, "n/a", "n/a", "n/a", rounds,
                    "环境不可用或异常，已跳过: " + e.getMessage());
        }
    }

    private ValidationReport skipped() {
        return new ValidationReport(false, false, "n/a", "n/a", "n/a", 0, "已跳过（lecture.validate=false）");
    }

    // ===================== LLM 调用 =====================

    private String chat(String systemPrompt, String userMessage) {
        ChatRequest request = ChatRequest.builder()
                .messages(SystemMessage.from(systemPrompt), UserMessage.from(userMessage))
                .build();
        ChatResponse response = chatModel.chat(request);
        return response.aiMessage().text();
    }

    // ===================== user message 构造 =====================

    private String buildBeikeUser(LectureRequest req, String pid, String budget, String outDir, String sample) {
        StringBuilder sb = new StringBuilder();
        if (sample != null) {
            sb.append("【备课样例（开工前参考 1 份）】\n").append(sample).append("\n\n");
        }
        sb.append("【本次题目输入】\n");
        sb.append("- problem_id: ").append(pid).append("\n");
        sb.append("- statement:\n").append(req.problem()).append("\n");
        sb.append("- answer_hint: ").append(blank(req.answerHint()) ? "（无）" : req.answerHint()).append("\n");
        sb.append("- budget: ").append(budget).append("\n");
        sb.append("- output_dir: ").append(outDir).append("\n\n");
        sb.append("【环境说明】本环境已把样例附在上方，无需再读样例文件；本地无 Python 校验，请跳过「开工前抽样读样例」「运行自检」等步骤，依据本提示词核心规则与章节清单生成。请直接输出 ")
                .append(pid).append("_备课.md 的完整 Markdown 正文，不要输出「报告」段，不要用代码围栏包裹整体。");
        return sb.toString();
    }

    private String buildJianggaoUser(String pid, String budget, String outDir,
                                     String ttsRules, String sample, String beike) {
        StringBuilder sb = new StringBuilder();
        if (ttsRules != null) {
            sb.append("【TTS 读法约定（单一真源，必读）】\n").append(ttsRules).append("\n\n");
        }
        if (sample != null) {
            sb.append("【讲稿样例（开工前参考 1 份）】\n").append(sample).append("\n\n");
        }
        sb.append("【备课笔记 ").append(pid).append("_备课.md 内容】\n---\n")
                .append(beike).append("\n---\n\n");
        sb.append("【本次输入】\n- problem_id: ").append(pid)
                .append("\n- budget: ").append(budget)
                .append("\n- output_dir: ").append(outDir).append("\n\n");
        sb.append("【环境说明】tts_读法约定与样例已附上方，无需再读文件；本地无 Python/grep，请按提示词规则人工自检 TTS 残留，不要运行 grep 命令。请直接输出 ")
                .append(pid).append("_讲稿.md 的完整 Markdown 正文，不要「报告」段，不用代码围栏包裹整体。");
        return sb.toString();
    }

    private String buildYamlUser(String pid, String budget, String outDir, String ttsRules, String schemaSpec,
                                 String sample, String profile, String beike, String jianggao) {
        StringBuilder sb = new StringBuilder();
        if (ttsRules != null) {
            sb.append("【TTS 读法约定（单一真源，必读）】\n").append(ttsRules).append("\n\n");
        }
        if (schemaSpec != null) {
            sb.append("【schema 规范（字段全集）】\n").append(schemaSpec).append("\n\n");
        }
        if (sample != null) {
            sb.append("【yaml 样例（开工前参考 1 份）】\n").append(sample).append("\n\n");
        }
        if (profile != null) {
            sb.append("【成员讲题视频偏好】\n").append(profile).append("\n\n");
        }
        sb.append("【备课笔记 ").append(pid).append("_备课.md 内容】\n---\n")
                .append(beike).append("\n---\n\n");
        sb.append("【讲稿 ").append(pid).append("_讲稿.md 内容】\n---\n")
                .append(jianggao).append("\n---\n\n");
        sb.append("【本次输入】\n- problem_id: ").append(pid)
                .append("\n- title: 题目讲解\n- mode: full\n- budget: ").append(budget)
                .append("\n- output_dir: ").append(outDir).append("\n\n");
        sb.append("【环境说明】tts_读法约定/schema规范/样例均已附上方，无需再读文件；本地无 Python，请按提示词规则做纯文本自检（逐条人工核对），不要运行 grep/python 命令；schema 校验与渲染由下游处理。请直接输出 ")
                .append(pid).append(".yaml 的完整 YAML 正文，不要「报告」段，不用 markdown 代码围栏包裹整体。");
        return sb.toString();
    }

    private String buildFixUser(String fileName, String currentYaml, String feedback) {
        return "下面是已生成的 " + fileName + "，但本地 Python 校验未通过。请依据 yaml 编导提示词修正后，输出完整的 yaml 正文（不要 markdown 代码围栏）。\n\n"
                + "【校验反馈】\n" + feedback + "\n\n"
                + "【当前 yaml】\n---\n" + currentYaml + "\n---\n\n"
                + "请只修正校验反馈指出的问题，保持其余内容不变，输出完整 yaml。";
    }

    // ===================== 多题批量生成（SSE 并发） =====================

    /** 题目分隔符：单独一行的 --- */
    private static final Pattern PROBLEM_SEP = Pattern.compile("(?m)^---\\s*$");
    private static final Pattern TYPE_RE = Pattern.compile("###\\s*【(.+?)】");
    private static final Pattern STEM_RE = Pattern.compile("【题干】([^\\n]*)");

    /** 一道切分后的题目。 */
    public record ProblemBlock(int index, String text, String type, String preview) {
    }

    /**
     * 把多题文档切成多块。规则：按单独一行 {@code ---} 切分；丢弃不含 {@code 【题干】} 的块
     * （如文件顶部的 {@code # 标题}）；每块截到首个 {@code ###} 之后，剥掉前面的 H1/H2 标题。
     */
    public List<ProblemBlock> splitProblems(String document) {
        List<ProblemBlock> blocks = new ArrayList<>();
        if (document == null || document.isBlank()) {
            return blocks;
        }
        String[] parts = PROBLEM_SEP.split(document);
        int idx = 0;
        for (String p : parts) {
            String block = stripBeforeFirstHeading(p).trim();
            if (block.isEmpty() || !block.contains("【题干】")) {
                continue;
            }
            blocks.add(new ProblemBlock(idx++, block, extractType(block), extractPreview(block)));
        }
        return blocks;
    }

    private String stripBeforeFirstHeading(String p) {
        int i = p.indexOf("###");
        return i >= 0 ? p.substring(i) : p;
    }

    private String extractType(String block) {
        Matcher m = TYPE_RE.matcher(block);
        return m.find() ? m.group(1) : "题目";
    }

    private String extractPreview(String block) {
        Matcher m = STEM_RE.matcher(block);
        String s = m.find() ? m.group(1) : block;
        s = s.replaceAll("\\s+", " ").trim();
        return s.length() > 60 ? s.substring(0, 60) + "…" : s;
    }

    /**
     * 多题并发生成，逐题通过 SSE 推送进度。事件序列：
     * {@code start}（total）-> 每题 {@code start-item} -> 每题 {@code item}（含 result 或 error）-> {@code done}。
     *
     * <p>并发度受 {@code concurrency}（或配置 {@code lecture.batch-concurrency}）限制；单题失败不影响其它题。
     * 每题复用 {@link #generate(LectureRequest)}，problemId 形如 {@code 前缀_01}。
     */
    public void generateBatch(LectureBatchRequest req, SseEmitter emitter) {
        String prefix = blank(req.problemIdPrefix()) ? "problem_" + System.currentTimeMillis() : req.problemIdPrefix();
        String budget = blank(req.budget()) ? "标准" : req.budget();
        String outDir = blank(req.outputDir()) ? outputDir : req.outputDir();
        int concurrency = (req.concurrency() == null || req.concurrency() < 1) ? batchConcurrency : req.concurrency();

        List<ProblemBlock> blocks = splitProblems(req.document());
        int n = blocks.size();
        int width = Math.max(2, String.valueOf(n).length());
        int poolSize = Math.min(concurrency, Math.max(1, n));

        try {
            emitter.send(SseEmitter.event().name("start").data(Map.of("total", n, "concurrency", poolSize)));
        } catch (IOException e) {
            emitter.completeWithError(e);
            return;
        }
        if (n == 0) {
            try {
                emitter.send(SseEmitter.event().name("done").data(Map.of("total", 0, "succeeded", 0, "failed", 0)));
                emitter.complete();
            } catch (IOException e) {
                emitter.completeWithError(e);
            }
            return;
        }

        ExecutorService pool = Executors.newFixedThreadPool(poolSize);
        AtomicInteger succeeded = new AtomicInteger();
        AtomicInteger failed = new AtomicInteger();
        AtomicBoolean clientGone = new AtomicBoolean(false);
        List<CompletableFuture<Void>> futures = new ArrayList<>();

        for (ProblemBlock b : blocks) {
            final ProblemBlock block = b;
            final String problemId = prefix + "_" + String.format("%0" + width + "d", block.index() + 1);
            CompletableFuture<Void> f = CompletableFuture.runAsync(() -> {
                if (clientGone.get()) {
                    return; // 客户端已断开，跳过尚未开始的题目
                }
                try {
                    emitter.send(SseEmitter.event().name("start-item").data(Map.of(
                            "index", block.index(), "problemId", problemId,
                            "type", block.type(), "preview", block.preview())));
                } catch (IOException e) {
                    clientGone.set(true);
                    return; // 客户端断开，不再生成
                }
                try {
                    LectureRequest lr = new LectureRequest(block.text(), problemId, null, budget, outDir, req.memberName());
                    LectureResult r = generate(lr);
                    succeeded.incrementAndGet();
                    emitter.send(SseEmitter.event().name("item").data(Map.of(
                            "index", block.index(), "ok", true, "result", r)));
                } catch (Exception e) {
                    failed.incrementAndGet();
                    log.warn("题目 {} 生成失败: {}", problemId, e.getMessage(), e);
                    String msg = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
                    try {
                        emitter.send(SseEmitter.event().name("item").data(Map.of(
                                "index", block.index(), "ok", false, "problemId", problemId, "error", msg)));
                    } catch (IOException ignored) {
                        clientGone.set(true);
                    }
                }
            }, pool);
            futures.add(f);
        }

        final int total = n;
        CompletableFuture.allOf(futures.toArray(new CompletableFuture[0])).whenComplete((v, ex) -> {
            try {
                emitter.send(SseEmitter.event().name("done").data(Map.of(
                        "total", total, "succeeded", succeeded.get(), "failed", failed.get())));
                emitter.complete();
            } catch (IOException e) {
                emitter.completeWithError(e);
            } finally {
                pool.shutdown();
            }
        });
    }

    // ===================== 工具 =====================

    private String readSkill(String name) throws IOException {
        return Files.readString(Paths.get(skillsDir, name), StandardCharsets.UTF_8);
    }

    /** 读取引用文件；缺失返回 null（best-effort，不阻塞主流程）。 */
    private String readResource(Path base, String relative) {
        try {
            Path p = base.resolve(relative);
            return Files.exists(p) ? Files.readString(p, StandardCharsets.UTF_8) : null;
        } catch (IOException e) {
            log.warn("读取引用失败，跳过: {}/{}", base, relative);
            return null;
        }
    }

    private String beikeSampleName(String budget) {
        return switch (budget) {
            case "简洁" -> "problem_01_备课.md";
            case "深入" -> "problem_19_备课.md";
            default -> "problem_17_备课.md";
        };
    }

    private String yamlSampleName(String budget) {
        return "深入".equals(budget) ? "直三棱柱-向量法求平面夹角-T1.yaml" : "simple_fast_complex_subtraction.yaml";
    }

    /** 剥掉模型可能包裹的最外层 markdown 代码围栏（仅用于 yaml）。 */
    private String stripCodeFence(String text) {
        if (text == null) {
            return text;
        }
        String t = text.strip();
        if (t.startsWith("```")) {
            int nl = t.indexOf('\n');
            if (nl > 0) {
                t = t.substring(nl + 1);
            }
            if (t.endsWith("```")) {
                t = t.substring(0, t.length() - 3);
            }
            return t.strip();
        }
        return text;
    }

    private static boolean blank(String s) {
        return s == null || s.isBlank();
    }
}
