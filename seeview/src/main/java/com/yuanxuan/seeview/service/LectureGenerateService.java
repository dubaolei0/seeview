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
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
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
 * <p>可选的用户补充要求（{@code extraInstructions} + {@code bannedWords}）注入备课、讲稿与
 * 简洁（fast）模式 yaml 三处；标准模式 yaml 台词来自讲稿，不重复注入。备课/讲稿/fast yaml
 * 落盘前各做一次禁用词字面量检查，命中则回传大模型修正一轮。
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

        // 题干里的本地图片引用（![...](C:\...png)）复制到输出目录，改写为稳定绝对路径（正斜杠），
        // 之后注入提示词的 statement / 发给大模型的题目文本都指向副本，原图被移动/删除不影响后续渲染
        StabilizedProblem sp = stabilizeImages(req.problem(), outPath, problemId);
        String problem = sp.text();
        List<String> problemImages = sp.images();

        String yamlPrompt = readSkill("yaml.md");
        boolean concise = "简洁".equals(budget); // 简洁：只生成 yaml（fast 模式，无备课/讲稿）

        // 读注入引用（缺失则跳过，不阻塞）
        String ttsRules = readResource(pipelineDir, "rules/tts_读法约定.md");
        String schemaSpec = readResource(pipelineDir, "docs/schema规范.md");
        String yamlSample = readResource(pipelineDir.resolve("samples/yaml样例"), yamlSampleName(budget));
        String profile = blank(req.memberName()) ? null
                : readResource(Paths.get(communityDir), "team/" + req.memberName() + "/profile.md");

        String beike = null, jianggao = null;
        Path beikePath = null, jianggaoPath = null;

        // 用户补充要求：清洗一次，备课/讲稿/fast yaml 三处共用
        String extra = truncateExtra(req.extraInstructions());
        List<String> banned = sanitizeBannedWords(req.bannedWords());

        if (!concise) {
            // 标准 / 深入：三段式，先生成备课、讲稿
            String beikePrompt = readSkill("备课.md");
            String jianggaoPrompt = readSkill("讲稿.md");
            String beikeSample = readResource(pipelineDir.resolve("samples/备课样例"), beikeSampleName(budget));
            String jianggaoSample = readResource(pipelineDir, "samples/自然语言讲稿/problem_18_讲稿.md");

            // ① 备课
            beike = enforceBannedWords(beikePrompt, problemId + "_备课.md",
                    chat(beikePrompt, buildBeikeUser(req, problem, problemId, budget, outPath.toString(), beikeSample, extra, banned)),
                    banned);
            beikePath = outPath.resolve(problemId + "_备课.md");
            Files.writeString(beikePath, beike, StandardCharsets.UTF_8);

            // ② 讲稿
            jianggao = enforceBannedWords(jianggaoPrompt, problemId + "_讲稿.md",
                    chat(jianggaoPrompt, buildJianggaoUser(problemId, budget, outPath.toString(), ttsRules, jianggaoSample, beike, extra, banned)),
                    banned);
            jianggaoPath = outPath.resolve(problemId + "_讲稿.md");
            Files.writeString(jianggaoPath, jianggao, StandardCharsets.UTF_8);
        }

        // ③ yaml（标准=full 模式带备课/讲稿；简洁=fast 模式直接由题目编导）
        String yaml = chat(yamlPrompt, concise
                ? buildYamlUserFast(problem, req, problemId, budget, outPath.toString(), ttsRules, schemaSpec, yamlSample, profile, problemImages, extra, banned)
                : buildYamlUser(problemId, budget, outPath.toString(), ttsRules, schemaSpec, yamlSample,
                        profile, beike, jianggao, problemImages));
        yaml = cleanYaml(yaml);
        // fast 模式无备课/讲稿兜底，yaml 本身做禁用词校验；标准模式已由讲稿校验覆盖
        if (concise) {
            yaml = cleanYaml(enforceBannedWords(yamlPrompt, problemId + ".yaml", yaml, banned));
        }
        Path yamlPath = outPath.resolve(problemId + ".yaml");
        Files.writeString(yamlPath, yaml, StandardCharsets.UTF_8);

        // ④ 题干图片兜底：题目带图但 yaml 未用 figure.type=image 引用时，定向修正一轮
        //（标准模式 yaml 只见备课/讲稿，备课可能改画 schematic/geometry3d，图片路径就此丢失）
        if (!problemImages.isEmpty() && !yaml.contains("type: image")) {
            log.info("题目 {} 带图片但 yaml 未引用 figure.type=image，触发定向修正", problemId);
            String fixed = chat(yamlPrompt, buildImageFixUser(yamlPath.getFileName().toString(), yaml, problemImages));
            Files.writeString(yamlPath, cleanYaml(fixed), StandardCharsets.UTF_8);
        }

        // ⑤ yaml 校验闭环
        ValidationReport report = validateEnabled ? validateLoop(yamlPath, yamlPrompt) : skipped();

        String finalYaml = Files.readString(yamlPath, StandardCharsets.UTF_8); // normalize_say 可能就地改写
        return new LectureResult(problemId,
                beikePath == null ? "" : beikePath.toString(),
                jianggaoPath == null ? "" : jianggaoPath.toString(),
                yamlPath.toString(),
                beike == null ? "" : beike,
                jianggao == null ? "" : jianggao,
                finalYaml, report);
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
                Files.writeString(yamlPath, cleanYaml(fixed), StandardCharsets.UTF_8);
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

    private String buildBeikeUser(LectureRequest req, String problem, String pid, String budget, String outDir,
                                  String sample, String extra, List<String> banned) {
        StringBuilder sb = new StringBuilder();
        if (sample != null) {
            sb.append("【备课样例（开工前参考 1 份）】\n").append(sample).append("\n\n");
        }
        appendUserRules(sb, extra, banned);
        sb.append("【本次题目输入】\n");
        sb.append("- problem_id: ").append(pid).append("\n");
        sb.append("- statement:\n").append(problem).append("\n");
        sb.append("- answer_hint: ").append(blank(req.answerHint()) ? "（无）" : req.answerHint()).append("\n");
        sb.append("- budget: ").append(budget).append("\n");
        sb.append("- output_dir: ").append(outDir).append("\n\n");
        sb.append("【环境说明】本环境已把样例附在上方，无需再读样例文件；本地无 Python 校验，请跳过「开工前抽样读样例」「运行自检」等步骤，依据本提示词核心规则与章节清单生成。请直接输出 ")
                .append(pid).append("_备课.md 的完整 Markdown 正文，不要输出「报告」段，不要用代码围栏包裹整体。");
        return sb.toString();
    }

    private String buildJianggaoUser(String pid, String budget, String outDir,
                                     String ttsRules, String sample, String beike, String extra, List<String> banned) {
        StringBuilder sb = new StringBuilder();
        if (ttsRules != null) {
            sb.append("【TTS 读法约定（单一真源，必读）】\n").append(ttsRules).append("\n\n");
        }
        if (sample != null) {
            sb.append("【讲稿样例（开工前参考 1 份）】\n").append(sample).append("\n\n");
        }
        appendUserRules(sb, extra, banned);
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
                                 String sample, String profile, String beike, String jianggao, List<String> images) {
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
        appendImageDirective(sb, images);
        sb.append("【备课笔记 ").append(pid).append("_备课.md 内容】\n---\n")
                .append(beike).append("\n---\n\n");
        sb.append("【讲稿 ").append(pid).append("_讲稿.md 内容】\n---\n")
                .append(jianggao).append("\n---\n\n");
        sb.append("【本次输入】\n- problem_id: ").append(pid)
                .append("\n- title: 题目讲解\n- mode: full\n- budget: ").append(budget)
                .append("\n- output_dir: ").append(outDir).append("\n\n");
        sb.append("【环境说明】tts_读法约定/schema规范/样例均已附上方，无需再读文件；本地无 Python，请按提示词规则做纯文本自检（逐条人工核对），不要运行 grep/python 命令；schema 校验与渲染由下游处理。请直接输出 ")
                .append(pid).append(".yaml 的完整 YAML 正文，不要「报告」段，不用 markdown 代码围栏包裹整体。回包第一行必须是 `core:`，前面禁止任何叙述/定位/核对（如「我先找到 yaml 文件」「校验反馈只指向 core: 行…」），思考在心里完成，只给成品 yaml。");
        return sb.toString();
    }

    private String buildFixUser(String fileName, String currentYaml, String feedback) {
        return "下面是已生成的 " + fileName + "，但本地 Python 校验未通过。请依据 yaml 编导提示词修正后，输出完整的 yaml 正文（不要 markdown 代码围栏）。\n\n"
                + "【校验反馈】\n" + feedback + "\n\n"
                + "【当前 yaml】\n---\n" + currentYaml + "\n---\n\n"
                + "请只修正校验反馈指出的问题，保持其余内容不变，输出完整 yaml。回包第一行必须是 `core:`，禁止复述校验反馈或描述你改了什么，只给修好的完整 yaml。";
    }

    /**
     * 简洁预算（fast 模式）的 yaml user message：无备课/讲稿，由题目 statement + answer_hint 直接编导。
     */
    private String buildYamlUserFast(String problem, LectureRequest req, String pid, String budget, String outDir,
                                     String ttsRules, String schemaSpec, String sample, String profile,
                                     List<String> images, String extra, List<String> banned) {
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
        appendImageDirective(sb, images);
        appendUserRules(sb, extra, banned);
        sb.append("【本次输入】\n- problem_id: ").append(pid)
                .append("\n- title: 题目讲解\n- mode: fast\n- budget: ").append(budget)
                .append("\n- statement:\n").append(problem)
                .append("\n- answer_hint: ").append(blank(req.answerHint()) ? "（无）" : req.answerHint())
                .append("\n- output_dir: ").append(outDir).append("\n\n");
        sb.append("【环境说明】tts_读法约定/schema规范/样例均已附上方，无需再读文件；本地无 Python，请按提示词规则做纯文本自检（逐条人工核对），不要运行 grep/python 命令；schema 校验与渲染由下游处理。本题为 fast 模式（无备课/讲稿），请按 yaml 提示词「fast 模式」规则：先把答案做对，再自写口语 say（守 budget 上限，仍受全部 say 红线），figure 自判，排版/分幕/schema/自检与 full 一致。请直接输出 ")
                .append(pid).append(".yaml 的完整 YAML 正文，不要「报告」段，不用 markdown 代码围栏包裹整体。回包第一行必须是 `core:`，前面禁止任何叙述/定位/核对，只给成品 yaml。");
        return sb.toString();
    }

    // ===================== 用户补充要求（前台可配置） =====================

    /** 补充提示词最大长度（字符），防误粘贴长文撑爆上下文 */
    private static final int MAX_EXTRA_CHARS = 2000;
    /** 禁用词最大个数 */
    private static final int MAX_BANNED_WORDS = 50;

    /**
     * 用户补充要求注入块：不写则不加。措辞上明确「不豁免核心规则」，
     * 用户不能用这段话解除 TTS 读法约定、schema 红线等硬约束。
     */
    private void appendUserRules(StringBuilder sb, String extra, List<String> banned) {
        boolean hasExtra = extra != null && !extra.isBlank();
        boolean hasBanned = banned != null && !banned.isEmpty();
        if (!hasExtra && !hasBanned) {
            return;
        }
        sb.append("【用户补充要求（必须遵守；优先级高于风格建议，但不豁免上文核心规则与禁忌）】\n");
        if (hasExtra) {
            sb.append("- 内容与风格要求：\n").append(extra).append('\n');
        }
        if (hasBanned) {
            sb.append("- 禁用词（正文中一律不得出现，需要时换同义表达，题干原文引用除外）：")
                    .append(String.join("、", banned)).append('\n');
        }
        sb.append('\n');
    }

    /** 去首尾空白并截断到上限；空串返回 null。 */
    private String truncateExtra(String s) {
        if (s == null) {
            return null;
        }
        String t = s.strip();
        if (t.isEmpty()) {
            return null;
        }
        if (t.length() <= MAX_EXTRA_CHARS) {
            return t;
        }
        log.warn("用户补充提示词过长（{} 字符），已截断到 {}", t.length(), MAX_EXTRA_CHARS);
        return t.substring(0, MAX_EXTRA_CHARS);
    }

    /** 去空白、去重、截断到上限；只做字面量匹配，不支持通配/正则。 */
    private List<String> sanitizeBannedWords(List<String> words) {
        if (words == null || words.isEmpty()) {
            return List.of();
        }
        List<String> out = new ArrayList<>();
        for (String w : words) {
            if (w == null) {
                continue;
            }
            String t = w.strip();
            if (!t.isEmpty() && !out.contains(t)) {
                out.add(t);
            }
            if (out.size() >= MAX_BANNED_WORDS) {
                log.warn("禁用词超过 {} 个，已截断", MAX_BANNED_WORDS);
                break;
            }
        }
        return out;
    }

    /** 字面量命中检查：返回正文里实际出现的禁用词。 */
    private List<String> findBannedHits(String text, List<String> banned) {
        List<String> hits = new ArrayList<>();
        for (String w : banned) {
            if (text.contains(w)) {
                hits.add(w);
            }
        }
        return hits;
    }

    /**
     * 禁用词兜底：正文命中禁用词时回传大模型修正一轮（最多 1 轮）。
     * 修正后仍命中只 log warn 不再重试（通常只剩题干原文引用这类应保留的场景）。
     */
    private String enforceBannedWords(String systemPrompt, String fileName, String doc, List<String> banned) {
        if (banned == null || banned.isEmpty() || doc == null) {
            return doc;
        }
        List<String> hits = findBannedHits(doc, banned);
        if (hits.isEmpty()) {
            return doc;
        }
        log.info("{} 命中禁用词 {}，回传修正一轮", fileName, hits);
        String fixed = chat(systemPrompt, buildBannedFixUser(fileName, doc, hits));
        List<String> remain = findBannedHits(fixed, banned);
        if (!remain.isEmpty()) {
            log.warn("{} 禁用词修正后仍含 {}（多为题干原文引用，保留）", fileName, remain);
        }
        return fixed;
    }

    /** 禁用词修正轮 user message。 */
    private String buildBannedFixUser(String fileName, String doc, List<String> hits) {
        StringBuilder sb = new StringBuilder();
        sb.append("下面是已生成的 ").append(fileName).append("，但正文中出现了用户禁用词。\n\n")
                .append("【命中的禁用词】\n").append(String.join("、", hits)).append("\n\n")
                .append("【当前正文】\n---\n").append(doc).append("\n---\n\n")
                .append("请把禁用词替换为意思一致的自然表达，避免再次命中任何禁用词；")
                .append("唯一例外：禁用词若出现在题干原文引用中，保留题干原文不动。")
                .append("其余内容、结构与排版保持不变。");
        if (fileName.endsWith(".yaml")) {
            sb.append("请直接输出完整 YAML 正文，回包第一行必须是 `core:`，禁止 markdown 代码围栏与任何说明。");
        } else {
            sb.append("请直接输出完整 Markdown 正文，不要 markdown 代码围栏，不要任何说明或复述。");
        }
        return sb.toString();
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
                log.info("开始生成题目 {}", problemId);
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
                    LectureRequest lr = new LectureRequest(block.text(), problemId, null, budget, outDir,
                            req.memberName(), req.extraInstructions(), req.bannedWords());
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

    // ===================== 题干图片本地化 =====================

    /** markdown 图片引用：![alt](path)，path 内不含空白与括号 */
    private static final Pattern IMG_REF = Pattern.compile("!\\[[^\\]]*\\]\\(([^()\\s]+)\\)");
    /** 绝对本地路径：盘符（C:\ 或 C:/）或 UNC（\\host\share\…） */
    private static final Pattern LOCAL_PATH = Pattern.compile("^([A-Za-z]:[\\\\/]|\\\\\\\\).*");
    /** 可复制的图片扩展名白名单（与 SeeViewController 预览接口一致） */
    private static final Set<String> IMAGE_EXTS = Set.of(
            "png", "jpg", "jpeg", "gif", "bmp", "webp", "svg");

    /** 一道题稳定化后的文本与其携带的图片路径（输出目录副本、正斜杠绝对路径）。 */
    private record StabilizedProblem(String text, List<String> images) {
    }

    /** 题干图片注入块：yaml 阶段的硬指令（优先级高于备课「○、图形需求」的图类型选择）。 */
    private void appendImageDirective(StringBuilder sb, List<String> images) {
        if (images == null || images.isEmpty()) {
            return;
        }
        sb.append("【题干图片（硬性要求，优先级高于备课「○、图形需求」）】\n");
        sb.append("题干自带图片，已复制为下列稳定路径。core.figure 必须用其中第 1 张：\n");
        sb.append("figure:\n  type: image\n  path: <第 1 个路径，一字不改照抄>\n  show_in_read: true\n");
        sb.append("规则：path 不加引号、不改正反斜杠；statement 不得出现 ![](...) 图片语法；");
        sb.append("不要另画 schematic/geometry3d 重现题图（备课若选了其它图类型，以本条为准）。\n");
        for (String img : images) {
            sb.append("- ").append(img).append('\n');
        }
        sb.append("\n");
    }

    /** 题目带图但 yaml 未引用 figure.type=image 时的定向修正 user message。 */
    private String buildImageFixUser(String fileName, String currentYaml, List<String> images) {
        StringBuilder sb = new StringBuilder();
        sb.append("下面是已生成的 ").append(fileName)
                .append("，但题干自带图片，yaml 必须用 figure.type=image 引用原图（当前缺失或类型不对）。请修正：\n")
                .append("1. 把 core.figure 改为（path 照抄第 1 个路径，不加引号）：\n")
                .append("figure:\n  type: image\n  path: ").append(images.get(0)).append("\n  show_in_read: true\n")
                .append("2. statement 里不得出现 ![](...) 图片语法。\n")
                .append("3. 若有 beat 的 show 引用了旧 figure 图元（show: {type: figure, ref: ...}），删除该 show 字段、保留 say。\n")
                .append("4. 其余内容保持不变。\n\n");
        sb.append("【图片路径】\n");
        for (String img : images) {
            sb.append("- ").append(img).append('\n');
        }
        sb.append("\n【当前 yaml】\n---\n").append(currentYaml).append("\n---\n\n")
                .append("请输出修正后的完整 yaml 正文，不要 markdown 代码围栏。回包第一行必须是 `core:`，")
                .append("禁止复述说明或描述你改了什么，只给修好的完整 yaml。");
        return sb.toString();
    }

    /**
     * 把题目文本里的本地图片引用改写为输出目录副本的绝对路径（正斜杠）。
     *
     * <p>上传的 md 里图片常写成原图的绝对路径（如桌面 {@code ![](C:\...\T3.png)}），
     * 直接进 yaml 会随原图被移动/删除而失效。这里在生成前把图片复制到
     * {@code {outputDir}/images/{problemId}_img{N}_{原文件名}}，注入提示词的题目文本
     * 指向副本；路径统一正斜杠，避免 yaml 双引号里反斜杠转义出错。
     * 引用不存在/非图片时保留原文（log warn），不阻塞生成。
     *
     * @return 改写后的文本 + 成功复制的图片路径列表
     */
    private StabilizedProblem stabilizeImages(String text, Path outDir, String problemId) {
        if (text == null || !text.contains("![")) {
            return new StabilizedProblem(text, List.of());
        }
        Matcher m = IMG_REF.matcher(text);
        StringBuilder sb = new StringBuilder();
        List<String> images = new ArrayList<>();
        boolean changed = false;
        while (m.find()) {
            String ref = m.group(0);
            String path = m.group(1);
            Path copied = copyImageIfLocal(path, outDir, problemId, images.size() + 1);
            if (copied != null) {
                String stable = copied.toString().replace('\\', '/');
                images.add(stable);
                changed = true;
                ref = ref.replace(path, stable);
            }
            m.appendReplacement(sb, Matcher.quoteReplacement(ref));
        }
        m.appendTail(sb);
        return new StabilizedProblem(changed ? sb.toString() : text, images);
    }

    /**
     * 路径为本地绝对路径、扩展名在白名单内且文件存在时，复制到输出目录 images/ 下，
     * 返回副本路径；否则返回 null（保留原引用）。
     */
    private Path copyImageIfLocal(String path, Path outDir, String problemId, int seq) {
        try {
            if (!LOCAL_PATH.matcher(path).matches()) {
                return null;
            }
            Path src = Path.of(path);
            String name = src.getFileName() == null ? "" : src.getFileName().toString();
            int dot = name.lastIndexOf('.');
            String ext = dot > 0 ? name.substring(dot + 1).toLowerCase() : "";
            if (!IMAGE_EXTS.contains(ext)) {
                return null;
            }
            if (!Files.isRegularFile(src)) {
                log.warn("题目图片不存在，保留原引用: {}", path);
                return null;
            }
            Path imgDir = outDir.resolve("images");
            Files.createDirectories(imgDir);
            // 文件名里的路径非法字符替换为下划线，保留中文与常用字符
            String safeName = name.replaceAll("[^\\w.\\-\u4e00-\u9fa5]", "_");
            Path dst = imgDir.resolve(problemId + "_img" + seq + "_" + safeName);
            Files.copy(src, dst, StandardCopyOption.REPLACE_EXISTING);
            log.info("题目图片已复制: {} -> {}", path, dst);
            return dst;
        } catch (Exception e) {
            log.warn("复制题目图片失败，保留原引用: {} -> {}", path, e.getMessage());
            return null;
        }
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

    /** yaml 落盘前的统一清洗：去代码围栏 + 去前言 + 去多余的 YAML 文档分隔符。 */
    private String cleanYaml(String text) {
        return stripDocSeparators(stripPreamble(stripCodeFence(text)));
    }

    /**
     * 删除 yaml 根键 {@code core:} 之前的非 YAML 前言。
     *
     * <p>多小题题目时模型偶尔会先输出一段中文叙述 / 答案核对清单再写 yaml，导致
     * {@code yaml.safe_load} 报 {@code mapping values are not allowed here}。合法 yaml 的文档
     * 根固定从列 0 的 {@code core:} 起头（样例均如此，core 永不为缩进键），故以首个列 0 的
     * {@code core:} 行作为文档根起点：仅当其前面存在非 {@code #} 注释、非空白的「实内容」行时，
     * 才丢弃前导部分，从 {@code core:} 起保留其余内容逐字不动；没有 {@code core:} 或前言只是
     * 注释/空行时原样返回，避免误伤合法 yaml。
     */
    private String stripPreamble(String text) {
        if (text == null) {
            return text;
        }
        int coreIdx = -1;
        String[] lines = text.split("\n", -1);
        for (int i = 0; i < lines.length; i++) {
            if (lines[i].matches("^core:.*")) {
                coreIdx = i;
                break;
            }
        }
        if (coreIdx <= 0) {
            return text; // 无 core: 或 core 已在第 0 行 -> 无前言
        }
        boolean hasPreamble = false;
        for (int i = 0; i < coreIdx; i++) {
            String l = lines[i];
            if (l.isBlank() || l.trim().startsWith("#")) {
                continue;
            }
            hasPreamble = true;
            break;
        }
        if (!hasPreamble) {
            return text; // 前面只有注释/空行，保留
        }
        StringBuilder sb = new StringBuilder();
        for (int i = coreIdx; i < lines.length; i++) {
            sb.append(lines[i]).append(i + 1 < lines.length ? "\n" : "");
        }
        String result = sb.toString().strip();
        log.warn("已裁掉 yaml 前言（{} 行非 YAML 段落），从 core: 起作为文档根", coreIdx);
        return result;
    }

    /**
     * 移除列 1 的 YAML 文档分隔符 {@code ---}。模型偶尔会用 {@code ---} 把单个 yaml 切成多段
     * （例如把 core 与 teach 分两段），下游 {@code yaml.safe_load} 会报
     * {@code expected a single document in the stream}。本 schema 的字符串值均用引号或 {@code \n}
     * 转义、列 1 的 {@code ---} 不可能是内容，故剔除（缩进的 {@code ---} 视为块标量内容，保留）。
     */
    private String stripDocSeparators(String text) {
        if (text == null) {
            return text;
        }
        StringBuilder sb = new StringBuilder();
        text.lines().filter(line -> !line.matches("---\\s*")).forEach(line -> sb.append(line).append('\n'));
        return sb.toString().strip();
    }

    private static boolean blank(String s) {
        return s == null || s.isBlank();
    }
}
