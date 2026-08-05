package com.yuanxuan.seeview.service;

import com.yuanxuan.manim.config.ManimProperties;
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

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

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
