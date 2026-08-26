package com.yuanxuan.seeview.controller;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.yuanxuan.seeview.dto.ChatTurn;
import com.yuanxuan.seeview.dto.LectureBatchRequest;
import com.yuanxuan.seeview.dto.LectureRequest;
import com.yuanxuan.seeview.dto.LectureResult;
import com.yuanxuan.seeview.dto.QuestionGenerateRequest;
import com.yuanxuan.seeview.dto.QuestionPaper;
import com.yuanxuan.seeview.dto.StemFixRequest;
import com.yuanxuan.seeview.dto.TikzFixRequest;
import com.yuanxuan.seeview.service.LectureGenerateService;
import dev.langchain4j.data.message.SystemMessage;
import dev.langchain4j.data.message.UserMessage;
import dev.langchain4j.model.chat.request.ChatRequest;
import dev.langchain4j.model.chat.response.ChatResponse;
import dev.langchain4j.model.openai.OpenAiChatModel;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Slf4j
@RestController
@RequestMapping("/langchain")
public class LangChainController {

    @Autowired
    OpenAiChatModel chatModel;

    @Autowired
    private LectureGenerateService lectureGenerateService;

    /** 题目插图本地保存目录：远程图片下载、本地图片拷贝到此处，题目内链接改写为副本绝对路径 */
    @Value("${question.image-dir:${user.dir}/question_output/images}")
    private String questionImageDir;

    /** TikZ 配图编译用 python（lecture_pipeline venv，带 pdf2image/PIL/numpy） */
    @Value("${question.tikz-python:${user.dir}/lecture_pipeline/.venv/Scripts/python.exe}")
    private String tikzPython;

    /** TikZ -> PNG 编译脚本（xelatex 编译并裁剪透明背景） */
    @Value("${question.tikz-script:${user.dir}/tools/题目png生成工具/latex_snippet_tool.py}")
    private String tikzScript;

    private static final HttpClient HTTP_CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10)).build();
    /** 单张远程图片大小上限 20MB */
    private static final int MAX_IMAGE_BYTES = 20 * 1024 * 1024;
    private static final AtomicInteger IMG_SEQ = new AtomicInteger();
    /** Markdown 图片：![alt](src)，src 为不含空白的路径或 URL */
    private static final Pattern MD_IMAGE =
            Pattern.compile("!\\[([^\\]]*)\\]\\(([^)\\s]+)(?:\\s+\"[^\"]*\")?\\)");
    private static final Pattern REMOTE_IMAGE = Pattern.compile("(?i)^https?://.+");
    /** 本地绝对路径：盘符（C:\ 或 C:/）或 UNC（\\host\…） */
    private static final Pattern LOCAL_PATH = Pattern.compile("^[A-Za-z]:[\\\\/].*|^\\\\\\\\.*");
    /** codecogs 公式图片由前端还原为 LaTeX 渲染，不落地保存 */
    private static final Pattern CODECOGS_URL = Pattern.compile("(?i)codecogs\\.com");
    private static final Set<String> IMAGE_EXTS = Set.of(
            "png", "jpg", "jpeg", "gif", "bmp", "webp", "svg");

    @RequestMapping("/hello")
    public String hello() {
        return chatModel.chat("你好,今天周几");
    }

    /**
     * 讲题视频三段式生成：题目 -> 备课.md -> 讲稿.md -> yaml，并跑 Python 校验闭环。
     *
     * @param request 题目与参数（problem 必填）
     * @return 三份文档路径、正文与校验报告
     */
    @PostMapping("/lecture/generate")
    public LectureResult generate(@RequestBody LectureRequest request) throws IOException {
        if (request.problem() == null || request.problem().isBlank()) {
            throw new IllegalArgumentException("problem 不能为空");
        }
        return lectureGenerateService.generate(request);
    }

    /**
     * 多题批量生成（SSE）：上传一份含多道题的文档，后端按 {@code ---} 切分后并发生成，
     * 逐题推送 {@code start-item}/{@code item} 进度，最后 {@code done}。
     *
     * @param request 多题文档与参数（document 必填）
     * @return SSE 事件流
     */
    @PostMapping(value = "/lecture/generate-batch", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter generateBatch(@RequestBody LectureBatchRequest request) {
        if (request.document() == null || request.document().isBlank()) {
            throw new IllegalArgumentException("document 不能为空");
        }
        // 2h 超时：多题并发生成可能耗时较长
        SseEmitter emitter = new SseEmitter(7_200_000L);
        lectureGenerateService.generateBatch(request, emitter);
        return emitter;
    }

    /**
     * TikZ 配图重新编译（智能命题工作台"编辑配图"用）：前端改完 TikZ 源码后调此接口重出图。
     *
     * @param body {@code {"code": "TikZ 源码"}}
     * @return 成功 {@code {"path": PNG 绝对路径}}；失败 {@code {"error": 错误摘要}}（HTTP 均 200，前端按字段区分）
     */
    @PostMapping("/question/render-tikz")
    public Map<String, String> renderTikz(@RequestBody Map<String, String> body) {
        String code = body == null ? null : body.get("code");
        if (code == null || code.isBlank()) {
            return Map.of("error", "code 不能为空");
        }
        TikzResult r = compileTikz(sanitizeTikz(code.strip()));
        if (!r.ok()) {
            return Map.of("error", r.error() == null ? "TikZ 编译失败" : r.error());
        }
        return Map.of("path", r.path().toString().replace('\\', '/'));
    }

    /**
     * AI 修正配图（智能命题工作台"调整配图"对话用）：题干 + 当前 TikZ 源码 + 对话历史
     * 交给大模型按用户最新要求修正，修正结果直接编译为 PNG，一次请求同时返回新代码与新图。
     *
     * <p>模型输出的代码编译失败时，自动把错误信息回传模型重修一轮（与生题 JSON 修正同模式），
     * 仍失败才返回 error。
     *
     * @param request {@code {"stem": 题干, "code": TikZ 源码, "messages": [{role, content}]}}
     *                （messages 最新一条 user 即本次修改要求）
     * @return 成功 {@code {"code": 新源码, "note": 修改说明, "path": PNG 绝对路径}}；
     *         失败 {@code {"error": 错误摘要}}（HTTP 均 200，前端按字段区分）
     */
    @PostMapping("/question/fix-tikz")
    public Map<String, String> fixTikz(@RequestBody TikzFixRequest request) {
        String code = request == null ? null : request.code();
        String instruction = latestUserMessage(request == null ? null : request.messages());
        if (code == null || code.isBlank()) {
            return Map.of("error", "code 不能为空");
        }
        if (instruction == null) {
            return Map.of("error", "messages 缺少 user 修改要求");
        }

        // 依据题干判定学科，选用对应学科的 TikZ 绘图规范（与生题时同一套判定口径）
        String subject = detectSubject(request.stem(), null);
        String system = tikzFixSystemPrompt(subject);
        String raw = chat(system, tikzFixUserPrompt(request, instruction));
        String fixed = extractTikzCode(raw);
        String note = tikzFixNote(raw);
        if (fixed == null) {
            return Map.of("error", "大模型未返回 TikZ 代码，请重试");
        }
        TikzResult r = compileTikz(sanitizeTikz(fixed));
        if (!r.ok()) {
            // 编译失败：带错误信息回传重修一轮，要求最小修正不推翻结构
            String retry = chat(system, "你修改后的 TikZ 代码编译失败，错误信息如下：" + r.error()
                    + "\n请在该代码基础上做最小修正（不要推翻已有结构），重新输出修改说明与完整代码。你输出的代码：\n```tikz\n"
                    + fixed + "\n```");
            String retryCode = extractTikzCode(retry);
            if (retryCode == null) {
                return Map.of("error", "修正后的代码编译失败：" + r.error());
            }
            fixed = retryCode;
            note = tikzFixNote(retry);
            r = compileTikz(sanitizeTikz(fixed));
            if (!r.ok()) {
                return Map.of("error", "修正后的代码仍编译失败：" + r.error());
            }
        }
        return Map.of("code", fixed,
                "note", note.isBlank() ? "已按要求修改配图" : note,
                "path", r.path().toString().replace('\\', '/'));
    }

    /**
     * AI 修改题干（智能命题工作台"编辑题干"对话用）：当前题干 + 选项/答案参考 + 对话历史
     * 交给大模型按用户最新要求改写，一次请求返回新题干与修改说明。
     *
     * @param request {@code {"stem": 题干, "options": [], "answer": "", "note": "",
     *                "messages": [{role, content}]}}（messages 最新一条 user 即本次修改要求）
     * @return 成功 {@code {"stem": 新题干, "note": 修改说明}}；
     *         失败 {@code {"error": 错误摘要}}（HTTP 均 200，前端按字段区分）
     */
    @PostMapping("/question/fix-stem")
    public Map<String, String> fixStem(@RequestBody StemFixRequest request) {
        String stem = request == null ? null : request.stem();
        String instruction = latestUserMessage(request == null ? null : request.messages());
        if (stem == null || stem.isBlank()) {
            return Map.of("error", "stem 不能为空");
        }
        if (instruction == null) {
            return Map.of("error", "messages 缺少 user 修改要求");
        }

        String raw = chat(stemFixSystemPrompt(), stemFixUserPrompt(request, instruction));
        String fixed = extractStem(raw);
        if (fixed == null || fixed.isBlank()) {
            return Map.of("error", "大模型未返回题干，请重试");
        }
        return Map.of("stem", fixed,
                "note", stemFixNote(raw).isBlank() ? "已按要求修改题干" : stemFixNote(raw));
    }

    private String stemFixSystemPrompt() {
        return """
                你是一名资深命题专家。用户会给你一道题的当前题干（可能附选项、答案与解析作参考），以及对题干的修改要求
                （如替换情境、调整数字、修正表述、增删条件、改写提问方式等）。你的任务：在原题干基础上做最小必要修改，满足用户要求。

                修改原则：
                1. 只改用户指出的问题及其连带部分，不要重写整道题、不要改动与要求无关的内容；
                2. 题干必须与选项、答案保持逻辑一致；若修改导致答案或选项需要变化，不要自行改动选项、答案与解析，
                   在修改说明里明确提醒用户"答案/选项需同步调整"；
                3. 公式保持 LaTeX 记法：行内用 $...$ 包裹，独立公式用 $$...$$ 包裹，不要使用 Unicode 伪公式或纯文字描述公式；
                4. 题干中的图片链接与 ```tikz 代码块必须逐字保留（配图由专门的工具调整），除非用户明确要求改动配图；
                5. 输出修改后的完整题干（从第一个字到最后一个字），不要省略任何部分、不要添加题号。

                输出要求：先用一句话说明你改了什么（含答案/选项是否需同步调整的提醒），然后输出修改后的完整题干，
                用 ```stem 围栏代码块包裹，不要输出其他内容。
                """;
    }

    /** 题干修正请求用户提示词：当前题干 + 选项/答案参考 + 截断的对话历史 + 本次修改要求 */
    private String stemFixUserPrompt(StemFixRequest req, String instruction) {
        StringBuilder sb = new StringBuilder();
        sb.append("【当前题干】\n").append(req.stem().strip()).append('\n');
        if (req.options() != null && !req.options().isEmpty()) {
            sb.append("【选项】（保持题干与选项一致，不要改选项本身）\n");
            for (int i = 0; i < req.options().size(); i++) {
                sb.append((char) ('A' + i)).append("．").append(req.options().get(i)).append('\n');
            }
        }
        if (req.answer() != null && !req.answer().isBlank()) {
            sb.append("【答案】").append(req.answer().strip()).append('\n');
        }
        if (req.note() != null && !req.note().isBlank()) {
            sb.append("【解析】").append(req.note().strip()).append('\n');
        }
        appendHistory(sb, req.messages());
        sb.append("【本次修改要求】\n").append(instruction).append('\n');
        return sb.toString();
    }

    /**
     * 从大模型输出中抽取题干：取 ```stem 围栏块内容。题干自身可能内嵌 ```tikz 配图块，
     * 扫描时先跳过内层 tikz 块自身的闭合围栏，避免把内层闭合当成外层结束而截断题干。
     */
    private String extractStem(String raw) {
        if (raw == null || raw.isBlank()) return null;
        int open = raw.indexOf("```stem");
        if (open < 0) return null;
        int contentStart = raw.indexOf('\n', open);
        if (contentStart < 0) return null;
        contentStart++;
        int i = contentStart;
        while (i < raw.length()) {
            int fence = raw.indexOf("```", i);
            if (fence < 0) break;
            if (raw.startsWith("```tikz", fence)) {
                // 内层配图块：跳到它自己的闭合围栏之后
                int close = raw.indexOf("```", fence + 3);
                i = close < 0 ? raw.length() : close + 3;
            } else {
                // 外层（题干）闭合围栏
                return raw.substring(contentStart, fence).trim();
            }
        }
        // 未闭合：取到结尾（模型偶尔漏收尾围栏）
        return raw.substring(contentStart).replaceFirst("```\\s*$", "").trim();
    }

    /** 题干修改说明：```stem 围栏块之前的一句话；没有返回空串 */
    private String stemFixNote(String raw) {
        if (raw == null) return "";
        int open = raw.indexOf("```stem");
        String note = (open >= 0 ? raw.substring(0, open) : raw).replace("```", "").strip();
        return note.length() > 200 ? note.substring(0, 200) + "…" : note;
    }

    /** 对话历史上限：更早轮次的修改已体现在当前代码里，截掉省 token */
    private static final int TIKZ_FIX_HISTORY_LIMIT = 6;

    /** 配图修正系统提示词：规范按题干学科选用（与生图时同一套） */
    private String tikzFixSystemPrompt(String subject) {
        return """
                你是一名 TikZ 配图修正专家。用户会给你一道题的题干、当前配图的 TikZ 源码，以及对配图的修改要求
                （如标签压线、方向错误、比例失调、虚实线遮挡关系不对等）。你的任务：在原有代码基础上做最小必要修改，满足用户要求。

                修改原则：
                1. 保持与题干一致：字母命名、数量关系、比例（题干说 AB=2、BC=1，图中 AB 就应约为 BC 的两倍长）；
                2. 只改用户指出的问题及其连带位置，不要重构整张图、不要改动与要求无关的部分；
                3. 严格遵守以下绘图规范（已按学科【%s】选用，与生图时相同）：
                """.formatted(subject) + tikzRulesForSubject(subject) + """
                输出要求：先用一句话说明你改了什么，然后输出修改后的完整 TikZ 代码（用 ```tikz 围栏代码块包裹，不要省略任何行）。
                不要输出其他内容。
                """;
    }

    /** 修正请求用户提示词：题干 + 当前源码 + 截断的对话历史 + 本次修改要求 */
    private String tikzFixUserPrompt(TikzFixRequest req, String instruction) {
        StringBuilder sb = new StringBuilder();
        if (req.stem() != null && !req.stem().isBlank()) {
            sb.append("【题干】\n").append(req.stem().strip()).append('\n');
        }
        sb.append("【当前 TikZ 源码】\n```tikz\n").append(req.code().strip()).append("\n```\n");
        appendHistory(sb, req.messages());
        sb.append("【本次修改要求】\n").append(instruction).append('\n');
        return sb.toString();
    }

    /** 追加截断的对话历史（用户反馈与历次修改说明，由早到晚）；仅一条时不输出 */
    private void appendHistory(StringBuilder sb, List<? extends ChatTurn> messages) {
        if (messages == null || messages.size() <= 1) return;
        sb.append("【对话历史】（用户反馈与历次修改说明，由早到晚）\n");
        int from = Math.max(0, messages.size() - TIKZ_FIX_HISTORY_LIMIT);
        for (int i = from; i < messages.size(); i++) {
            ChatTurn m = messages.get(i);
            if (m == null || m.content() == null || m.content().isBlank()) continue;
            String who = "assistant".equalsIgnoreCase(m.role()) ? "助手" : "用户";
            sb.append(who).append("：").append(m.content().strip()).append('\n');
        }
    }

    /** 对话历史里最新一条非空 user 消息（即本次修改要求）；没有则 null（题干/配图修正共用） */
    private String latestUserMessage(List<? extends ChatTurn> messages) {
        if (messages == null) return null;
        String latest = null;
        for (ChatTurn m : messages) {
            if (m != null && "user".equalsIgnoreCase(m.role())
                    && m.content() != null && !m.content().isBlank()) {
                latest = m.content().strip();
            }
        }
        return latest;
    }

    /**
     * 从大模型输出中抽取 TikZ 代码：优先取 ```tikz 围栏块；没有围栏时，
     * 若整体输出已像 TikZ 源码（含 \draw/\node 等命令）则视为纯代码输出；否则 null。
     */
    private String extractTikzCode(String raw) {
        if (raw == null || raw.isBlank()) return null;
        Matcher m = TIKZ_BLOCK.matcher(raw);
        if (m.find()) return m.group(1).trim();
        String text = raw.trim();
        if (text.contains("\\begin{tikzpicture}") || text.contains("\\draw")
                || text.contains("\\node") || text.contains("\\fill")
                || text.contains("\\coordinate")) {
            // 去掉残缺围栏的收尾
            return text.replaceFirst("```\\s*$", "").trim();
        }
        return null;
    }

    /** 修改说明：围栏块之前的一句话；没有围栏或没有说明返回空串 */
    private String tikzFixNote(String raw) {
        if (raw == null) return "";
        Matcher m = TIKZ_BLOCK.matcher(raw);
        int end = m.find() ? m.start() : 0;
        String note = raw.substring(0, end).replace("```", "").strip();
        return note.length() > 200 ? note.substring(0, 200) + "…" : note;
    }

    /**
     * 上传答案/解析插图（智能命题工作台）：保存到题目插图目录并返回绝对路径，
     * 前端以 ![...](path) 嵌入答案/解析文本，经 /seeview/local-image 渲染。
     *
     * @param file 图片文件（扩展名须在白名单内，最大 20MB）
     * @return 成功 {@code {"path": 图片绝对路径}}；失败 {@code {"error": 错误摘要}}（HTTP 均 200，前端按字段区分）
     */
    @PostMapping("/question/upload-image")
    public Map<String, String> uploadImage(@RequestParam("file") MultipartFile file) {
        if (file == null || file.isEmpty()) {
            return Map.of("error", "file 不能为空");
        }
        if (file.getSize() > MAX_IMAGE_BYTES) {
            return Map.of("error", "图片超过 20MB 上限");
        }
        String name = file.getOriginalFilename();
        String ext = extOfFileName(name);
        if (ext == null) {
            return Map.of("error", "不支持的图片类型（支持 png/jpg/jpeg/gif/bmp/webp/svg）");
        }
        try {
            Path dst = writeImage(file.getBytes(), ext, name);
            return Map.of("path", dst.toString().replace('\\', '/'));
        } catch (Exception e) {
            log.warn("答案插图保存失败: {}", e.getMessage());
            return Map.of("error", "图片保存失败: " + e.getMessage());
        }
    }

    /** 从上传文件名取白名单内的图片扩展名；识别不了返回 null */
    private String extOfFileName(String name) {
        if (name == null) return null;
        int dot = name.lastIndexOf('.');
        String ext = dot > 0 ? name.substring(dot + 1).toLowerCase() : "";
        return IMAGE_EXTS.contains(ext) ? ext : null;
    }

    /**
     * AI 生题（智能命题工作台）：依据上传材料与命题参数生成一组题目。
     *
     * <p>学科不单独指定，由大模型依据材料内容自动识别，任意学科通用；
     * 大模型只需产出 title/topic/sections，总题量由后端统计补齐。
     *
     * @param request 题型、难度、题量、材料等（types 必填）
     * @return 题目组（含各题题干/选项/答案/解析，按题型分组）
     */
    @PostMapping("/question/generate")
    public QuestionPaper generateQuestions(@RequestBody QuestionGenerateRequest request) {
        if (request.types() == null || request.types().isEmpty()) {
            throw new IllegalArgumentException("types 不能为空");
        }

        // 先判定材料学科，再按学科选用对应的 TikZ 绘图规范
        String subject = detectSubject(request.content(), request.fileName());

        String system = questionSystemPrompt(request, subject);
        String raw = chat(system, questionUserPrompt(request, subject));
        QuestionPaper paper = parsePaper(raw);
        if (paper == null) {
            // 输出不是合法 JSON：回传修正一轮
            String fixed = chat(system,
                    "你上一次的输出不是合法 JSON 或不符合结构要求，请严格按要求的 JSON 结构重新输出，只输出 JSON 本体：\n"
                            + raw);
            paper = parsePaper(fixed);
        }
        if (paper == null) {
            throw new IllegalStateException("大模型返回的题目 JSON 无法解析，请重试");
        }
        // 题目里的图片落地保存（远程下载/本地拷贝），链接改写为副本路径
        paper = persistImages(paper);
        // 题干中的 ```tikz 代码块编译为配图 PNG，代码块改写为图片链接
        paper = renderTikzFigures(paper);
        return finalizePaper(paper, request);
    }

    // ===================== AI 生题：提示词与解析 =====================

    /** 解析大模型题目 JSON：忽略未知字段 */
    private static final ObjectMapper QUESTION_MAPPER = new ObjectMapper()
            .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);

    /** TikZ 绘图规范：通用部分（所有学科共用）：AI 生题提示词与配图对话修正提示词共用，调整时两处同步生效 */
    private static final String TIKZ_COMMON_RULES = """
            【通用底线】几何顶点必须用 \\coordinate (A) at (...); 定义，禁止用 \\node (A) at (...) {A}; 同时承担顶点和标签；
              所有连线只能连接 coordinate 名称，如 \\draw (A)--(B); 不要连接文字标签节点；
              顶点标签必须单独写成 \\node[below left=2pt, fill=white, inner sep=1pt] at (A) {A};
              标签根据相邻线段方向选择 above/below/left/right/above left/below right 等方位，避免压线；
              代码中的节点标签：纯文字标签（如 A、B、E）不用 $ 包裹；
              含下标/上标的标签必须整体用 $ 包裹成数学模式，如 \\node[left] at (A1) {$A_1$}，严禁写裸下标 \\node[left] at (A1) {A_1}；
              若一个点有两条以上线段相连，标签必须放在这些线段夹角外侧，不得放在线段经过方向上；
              线条粗细统一：整幅图统一用一种线宽（如 \\draw[thick] 或 \\draw[line width=0.8pt]），不要有的粗有的细；
              标签字体大小统一；字号只能写在节点选项里（如 every node/.style={font=\\small} 或 \\node[font=\\small,...]），严禁把 small、normalsize、\\small 等字号词写进标签内容里（错误示例：{smallA}、{smallD_1}、{\\small A}）；
              every node/.style 里的字体必须用 font=\\small 这种 key=value 写法，禁止直接写 {\\small}（会触发无限递归导致编译失败）；
              比例必须与题目给出的数量关系一致：题目说 AB=2、BC=1，图中 AB 就应当大约是 BC 的两倍长；
              题干条件（数值、单位、等量关系）一律写在题干文字里，禁止把题目条件直接标注在配图上；
              图中只出现字母、符号、单位、必要的直角/角标等辅助记号；
              有向线段/向量箭头必须使用 shorten >=2pt, shorten <=2pt，避免箭头直接插入端点圆心；若端点还要用 \fill 画实心点，箭头端点不得被 \fill 实心点覆盖，应先画普通线/点再画带 shorten 的箭头或适当缩短箭头；内部点标签必须避开箭头和三角形边，必要时改用 above left/above right/below left/below right 并增大 3pt~5pt 偏移，不得用白底标签遮住箭头、点或线段；
              必要时加大 scale 或拉大坐标间距，相邻顶点标签方位错开；
              注意字母与图形不要重叠（保留一定的距离）；
            【标签防重叠·强制】图中任何字母、数字不得与线段、箭头、曲线、其他标签重叠压盖，具体执行：
              方位词必须带显式偏移量：写成 below=3pt、above=3pt、left=3pt、right=3pt、below left=3pt 等，
                禁止裸写 below/above/left/right（默认偏移近似为 0，标签必然贴线重叠）；
              所有标签一律加白底衬底提高可读性：\\node[above=3pt, fill=white, inner sep=1.5pt]；
                白底只作衬底，仍须按方位偏移避开关键元素，禁止靠白底盖住箭头端点、实心点；
              线段上的标注（midway/pos）必须向线段一侧偏移：\\node[midway, above=3pt, fill=white, inner sep=1.5pt]，
                禁止把长度、数值、字母正压在线上或箭杆上；
              长度/数值/角度标注（如 2、5cm、60°）放在图形外侧，同一区域多个标签错开方位；
              箭头旁的物理量标签（如 v、F、B）放在箭头延长线一侧并偏移 3pt 以上，不压箭杆与箭头；
              带标签的相邻点间距至少 1.5cm~2cm，标签拥挤时优先加大 scale（如 scale=1.5）或拉大坐标间距，
                严禁通过缩小字号腾空间；字号全图统一，不得为避让重叠单独改小某个标签；
            """;

    /** TikZ 绘图规范：数学（生题与配图修正按学科选用） */
    private static final String TIKZ_RULES_MATH = """
            【高中数学】
              y轴水平向右，z轴竖直向上，x轴与y轴正方向夹角135度（或45度），y轴z轴线段长度不变，平行于x轴的线段长度取原长的二分之一；
              直棱柱、棱锥、圆柱、圆锥等几何体：先判断视角下每条棱的可见性，看得见的棱用实线，看不见的棱用虚线；凡被前方面、实体或线段遮挡的棱必须用虚线，被前方面、实体或线段遮挡的几何体自身棱必须用细虚线（dashed）；背面竖棱、背面底边、体内辅助线段若被遮挡也必须用虚线；不要把所有棱都画成 thick 实线；
              长方体/直棱柱斜二测可见性判定：外轮廓可见竖棱如 C--C1 必须用实线，不得仅因位于后侧就画虚线；虚线只用于真正被实体前方面遮住的几何体自身棱或背面棱；不要把后侧边链一概画成 dashed；顶点和标签不得互相遮挡，若 B 等顶点被遮挡，必须调整视角、坐标或标签位置，不能用白底标签盖住线段或顶点；
              棱锥可见性判定：底面后边、从顶点连到背侧底点且被前方面遮挡的棱必须用 dashed；前轮廓底边、可见侧棱必须用实线；不要按“底面边都实线”或“所有侧棱都实线”偷懒。
              立体几何题图强制绘图规范（必须逐条遵守）：
              1. 标签标注规范：所有顶点字母标签放置在顶点的外侧，向外偏移；❌严禁标签压在线条上、❌严禁文字跨线段，文字和图形线条必须完全分离，不能重叠。
                棱锥标签避让模板：顶点字母必须放在棱锥外轮廓外侧，偏移量不小于 4pt；边长数字必须写成 node[midway, sloped, above=4pt, fill=white, inner sep=1.5pt]，放在线段外侧，不得直接压在线上。
              2. 虚实线铁律：①几何体自身棱：观察者视角可见棱 = 实线 \\draw；被几何体遮挡、藏在后方的实体棱 = 细虚线 \\draw[dashed]。
                ②题干指定的解题辅助连线（人为新增线段）：辅助连线也要按空间遮挡判定；位于可见表面或图形外侧的辅助线用实线，被几何体前方面遮挡的辅助线用 dashed，禁止无视遮挡关系一概画成实线。
              3. 点的约束：边上的点必须严格落在对应线段上，禁止悬浮、偏移。
              4. 完整性：题目题干、证明需要用到的全部线段必须完整画出，不得遗漏关键辅助线。
              5. 箭头规则：没有向量要求时，只画普通线段，禁止添加任何 -> 向量箭头。
              6. 顶点命名严格遵循教材长方体 ABCD-A₁B₁C₁D₁ 对应规则，顶点顺序不能错乱。
              直角符号用小正方形（\\pgfsetcornersarced 或两条短线组成），不要用弧线表示直角；
              平面几何：角的弧线画在角内部，不压线；三角形高用虚线并加垂足直角标；
              函数图像：坐标轴带箭头、原点 O、x/y 标注；渐近线用虚线；关键交点、顶点、极值点标出坐标，不要跑出坐标轴区域范围，坐标轴要用实线带箭头并标出x轴和y轴；
              抛物线开口方向、对称轴与方程一致；双曲线两支对称，渐近线位置正确；
              三角函数：单位圆：单位圆半径 1，圆心在原点；角度从 x 轴正方向逆时针量起；
              向量：图里的向量要有Stealth 箭头，题干里向量符号用overrightarrow，箭头在终点，方向与坐标一致；空间直角坐标系用右手系，三轴方向固定，图中不需要显示基底；
              题目中的图形图片，只根据题干条件进行标注，不要涉及到解题过程中的中间量；
            """;

    /** TikZ 绘图规范：物理（生题与配图修正按学科选用） */
    private static final String TIKZ_RULES_PHYSICS = """
            【高中物理】
              受力分析：力的箭头从作用点出发，方向正确，长度大致与大小成正比；
              支持力垂直于接触面，摩擦力沿接触面，重力竖直向下；
              滑轮、绳子张力方向沿绳；弹簧画成均匀螺旋；
              运动学：v-t 图、x-t 图坐标轴带单位，斜率与加速度/速度一致，数值标注准确；
              平抛/斜抛轨迹画成抛物线，初速度方向正确；
              电磁学：电场线从正电荷出发到负电荷，不交叉，方向用箭头标注；
              磁感线闭合，外部 N→S，内部 S→N；
              电路：元件符号规范（电阻、电源、开关、电流表、电压表），导线横平竖直，节点用实心圆点；
              安培力、洛伦兹力方向与左手定则一致；
              光学：光线带箭头，折射/反射方向符合定律；凸透镜双凸、凹透镜双凹，焦点标 F；
              热学 / 原子：p-V 图、p-T 图、V-T 图坐标轴标注清楚，等压/等容/等温过程标注正确；
            """;

    /** TikZ 绘图规范：化学（生题与配图修正按学科选用） */
    private static final String TIKZ_RULES_CHEMISTRY = """
            【高中化学】
              原子结构 / 电子排布：原子核在中心，电子层为同心圆，能级图横线对齐，电子箭头（↑↓）规范；
              分子结构 / 化学键：球棍模型、比例模型区分清楚；键角大致符合实际（如水 ~104.5°、甲烷 109.5°）；
              实验装置：试管、烧杯、酒精灯、导管、集气瓶用标准画法；装置连接顺序正确，接口处对齐；
              加热用火焰符号标注，长管进短管出等洗气规则正确；
              化学平衡 / 反应速率图：浓度-时间图、速率-时间图坐标轴带单位，拐点、平衡点标注正确）。
            """;

    /** 按学科选配 TikZ 绘图规范：通用规范 + 对应学科规范；未识别的学科带全部分科规范兜底 */
    private String tikzRulesForSubject(String subject) {
        if (subject == null) {
            return TIKZ_COMMON_RULES + TIKZ_RULES_MATH + TIKZ_RULES_PHYSICS + TIKZ_RULES_CHEMISTRY;
        }
        return switch (subject) {
            case "数学" -> TIKZ_COMMON_RULES + TIKZ_RULES_MATH;
            case "物理" -> TIKZ_COMMON_RULES + TIKZ_RULES_PHYSICS;
            case "化学" -> TIKZ_COMMON_RULES + TIKZ_RULES_CHEMISTRY;
            default -> TIKZ_COMMON_RULES + TIKZ_RULES_MATH + TIKZ_RULES_PHYSICS + TIKZ_RULES_CHEMISTRY;
        };
    }

    /** 学科分类提示词输入上限：材料截前 2000 字足够判断学科 */
    private static final int SUBJECT_CLASSIFY_LIMIT = 2000;

    /**
     * 依据材料文本（辅以文件名）判断学科：数学 / 物理 / 化学 / 其他，
     * 用于生题与配图修正时选用对应学科的 TikZ 绘图规范；失败或无法判断返回"其他"。
     */
    private String detectSubject(String content, String fileName) {
        String text = content == null ? "" : content.strip();
        if (text.isEmpty() && fileName != null && !fileName.isBlank()) {
            text = "（文件名：" + fileName.strip() + "）";
        }
        if (text.isEmpty()) return "其他";
        if (text.length() > SUBJECT_CLASSIFY_LIMIT) text = text.substring(0, SUBJECT_CLASSIFY_LIMIT);
        try {
            String raw = chat("""
                    你是学科分类助手。判断用户给出的材料属于哪个学科，只回答一个词：数学、物理、化学或其他。
                    不要输出任何解释、标点或其他内容。
                    """, text);
            if (raw != null) {
                if (raw.contains("数学")) return "数学";
                if (raw.contains("物理")) return "物理";
                if (raw.contains("化学")) return "化学";
            }
        } catch (Exception e) {
            log.warn("学科分类失败，绘图规范按全学科兜底: {}", e.getMessage());
        }
        return "其他";
    }

    private String questionSystemPrompt(QuestionGenerateRequest req, String subject) {
        return """
                你是一名资深的命题专家，负责依据用户提供的材料生成一组高质量的学科检测题。命题要求：

                1. 先依据材料内容自动识别所属学科与核心考点，再围绕它们命题；学科不单独指定，以材料为准
                   （系统已初步判定学科为【%s】，明显有误时以材料实际内容为准）；
                2. 默认学段为高中，所有题目均按高中阶段的知识范围、难度要求和命题风格命制；
                   除非材料明确指向小学/初中/大学等其他学段，否则一律以高中课标为基准；
                3. 题目必须紧扣材料内容与知识点，不得照抄材料原文，考查理解与运用；
                4. 严格按用户指定的题型组合出题，把总题量合理分配到各题型；
                5. 难度整体贴合用户指定的难度档位（容易/中等/较难），可少量浮动；
                6. 科学严谨：题干表述清晰、无歧义，答案唯一且正确，解析简明扼要；
                7. 题干、选项、答案、解析中的学科术语、符号规范符合所命学科的惯例；
                8. 数学与物理公式一律使用 LaTeX 记法，行内公式用 $...$ 包裹，独立公式用 $$...$$ 包裹，不要使用 Unicode 伪公式或纯文字描述公式。
                   物理量符号规范：矢量用 \\vec{v}，单位用正体如 $\\mathrm{m/s^2}$，希腊字母用 \\omega、\\mu 等标准命令。
                9. 材料中若出现 codecogs 之类公式图片链接（如 ![公式图](https://latex.codecogs.com/svg.image?B_1E...)），
                   其问号后的内容是 URL 编码的 LaTeX，请解码还原为标准 LaTeX 公式写进题目，题目中不得保留任何公式图片链接。
                10. 高考题改编式命题：材料中的 XXX（知识点）、XX 与 XXX（数量、层级）由你依据材料和用户设置自动确定——
                   知识点取自材料考点，数量与层级对应用户指定的题量与难度档位。
                   （1）对于知识点关联相对充分的题目：请根据 XXX 知识点，挑选 XX 道高考题，并根据每道高考题在 XXX 层级改编 XXX 道题。
                       请围绕原题中的概念、公式、模型、具体应用等要素特征进行改编，可以替换原题中的数字，可以调整物理场景设定，
                       尽可能保留原始题目的特征和命题逻辑。如果题目配有图片，在已改编的题目中可以不使用图片、使用原图片，
                       或者在必要的情况下用 TikZ 重新绘制题目配图（系统会把 TikZ 代码自动编译为配图；
                       TikZ 代码用 ```tikz 围栏代码块包裹，放在题干末尾；因为最终输出是 JSON 字符串，TikZ 命令反斜杠必须写成 JSON 合法转义后的双反斜杠，例如输出 \\\\node、\\\\draw、\\\\coordinate，严禁输出会被 JSON 解析成换行的 \\node；
                       TikZ 绘图强制规范（已按学科【%s】选用对应规范，必须严格遵守）：
                """.formatted(subject, subject) + tikzRulesForSubject(subject) + """
                       若用户补充要求不得直接使用原图片，则必须用 TikZ 重绘配图、不得输出原图片链接；
                       重绘时按改编后的实际尺寸取比例，改编数字尽量打破原图的等比关系（如长宽高改为不同比例），
                       使新配图与原图有肉眼可辨的差异。
                       使用原图片时必须原样保留材料中的 Markdown 图片语法（如 ![](C:\\Users\\...\\T3.png) 的本地路径原样复制，不要改写或省略）；
                       不使用图片时题干中不得出现"如图"等指代图片的表述，需改写为不含图的说法。
                   （2）对于知识点关联不充分的题目：请围绕 XXX 题，根据 XXX 知识点进行改编。

                11. 解析配图：立体几何、平面几何、函数图像、圆、椭圆、双曲线、抛物线、运动过程、受力分析、电路、光路、实验装置等需要
                   图形辅助理解的题目，在解析（note 字段）的文字说明之后附一张 ```tikz 辅助图，
                   画出解题的关键元素（辅助线、截面、坐标系、运动轨迹、受力示意、等效电路等），帮助学生看懂解题过程；
                   TikZ 代码块放在 note 文字末尾，反斜杠转义规则与题干配图相同（JSON 里必须写成双反斜杠，如输出 \\\\node）；
                   绘图同样严格遵守上文 TikZ 强制规范；解析配图只画解题涉及的辅助元素与关键中间状态，
                   不要整幅重复题干已有的配图；纯计算、不需要图形辅助的题目不要强行配图。

                输出要求：只输出一个合法的 JSON 对象，不要输出任何其他文字或代码块标记，结构如下：
                {
                  "title": "题目集标题",
                  "topic": "考查主题（一句话）",
                  "sections": [
                    {
                      "type": "题型（与用户指定的题型名完全一致）",
                      "items": [
                        {
                          "q": "题干",
                          "o": ["选项一", "选项二", "选项三", "选项四"],
                          "a": "答案",
                          "note": "简要解析（一两句话；需要图形辅助理解的题目按第 11 条在末尾附 ```tikz 辅助图）",
                          "d": "难度（容易/中等/较难）"
                        }
                      ]
                    }
                  ]
                }

                字段约定：
                - "o" 仅客观题（单选题/多选题/判断题）提供，为字符串数组；判断题固定为 ["正确", "错误"]；填空题/解答题不要输出 "o" 字段；
                - "a" 为答案：单选题填字母（如 "A"），多选题填字母组合（如 "ABD"），判断题填 "正确" 或 "错误"，填空题填结果，解答题填要点式答案；
                - "note" 为红笔解析，需要图形辅助理解的题目按第 11 条在文字末尾附 ```tikz 辅助图；"d" 为该题难度。
                """;
    }

    private String questionUserPrompt(QuestionGenerateRequest req, String subject) {
        String difficulty = req.difficulty() == null || req.difficulty().isBlank() ? "中等" : req.difficulty();
        int count = req.count() == null ? 5 : Math.min(30, Math.max(1, req.count()));

        StringBuilder sb = new StringBuilder();
        sb.append("【学科判定】").append(subject).append('\n');
        sb.append("【题型组合】").append(String.join("、", req.types())).append('\n');
        sb.append("【总题量】").append(count).append(" 题\n");
        sb.append("【难度】").append(difficulty).append('\n');

        String content = req.content();
        if (content != null && !content.isBlank()) {
            sb.append("【命题材料】（请先识别材料所属学科，再依据材料命题）\n")
                    .append(content.strip()).append('\n');
        } else {
            String name = req.fileName() == null || req.fileName().isBlank() ? "" : "（文件名：" + req.fileName() + "）";
            sb.append("【命题材料】用户未提供可读的材料文本").append(name)
                    .append("，请结合文件名主题，生成一组综合复习检测题。\n");
        }
        if (req.prompt() != null && !req.prompt().isBlank()) {
            sb.append("【用户补充要求】").append(req.prompt().strip()).append('\n');
        }
        return sb.toString();
    }

    private String chat(String systemPrompt, String userMessage) {
        ChatRequest request = ChatRequest.builder()
                .messages(SystemMessage.from(systemPrompt), UserMessage.from(userMessage))
                .build();
        ChatResponse response = chatModel.chat(request);
        return response.aiMessage().text();
    }

    /** 解析大模型输出：剥掉代码块围栏，截取首尾大括号之间的 JSON 再反序列化 */
    private QuestionPaper parsePaper(String raw) {
        if (raw == null) return null;
        int start = raw.indexOf('{');
        int end = raw.lastIndexOf('}');
        if (start < 0 || end <= start) return null;
        try {
            QuestionPaper paper = QUESTION_MAPPER.readValue(raw.substring(start, end + 1), QuestionPaper.class);
            paper = normalizeLiteralLineBreakEscapes(paper);
            if (paper.sections() == null || paper.sections().isEmpty()) return null;
            return paper;
        } catch (Exception e) {
            return null;
        }
    }

    /**
     * 还原模型在嵌套 JSON 字符串中多转义的换行标记（\\n / \\r\\n）。
     * 不做简单全局替换，避免把 TikZ/LaTeX 命令如 \node、\neq 误改成换行 + 残缺命令。
     */
    private QuestionPaper normalizeLiteralLineBreakEscapes(QuestionPaper paper) {
        if (paper == null || paper.sections() == null) return paper;
        List<QuestionPaper.Section> sections = paper.sections().stream().map(sec -> {
            if (sec == null || sec.items() == null) return sec;
            List<QuestionPaper.Item> items = sec.items().stream().map(item -> {
                if (item == null) return null;
                return new QuestionPaper.Item(
                        normalizeLiteralLineBreakEscapes(item.q()),
                        item.o() == null ? null : item.o().stream().map(this::normalizeLiteralLineBreakEscapes).toList(),
                        normalizeLiteralLineBreakEscapes(item.a()),
                        normalizeLiteralLineBreakEscapes(item.note()),
                        item.d());
            }).toList();
            return new QuestionPaper.Section(sec.type(), items);
        }).toList();
        return new QuestionPaper(paper.title(), paper.topic(), paper.difficulty(),
                sections, paper.totalQ(), paper.source(), paper.prompt());
    }

    private String normalizeLiteralLineBreakEscapes(String text) {
        if (text == null || (!text.contains("\\n") && !text.contains("\\r"))) return text;
        return text.replaceAll("\\\\+r\\\\+n(?![A-Za-z])", "\n")
                .replaceAll("\\\\+r(?![A-Za-z])", "\n")
                .replaceAll("\\\\+n(?![A-Za-z])", "\n");
    }

    /** 补齐后端计算字段：难度、总题量、标题、主题、来源 */
    private QuestionPaper finalizePaper(QuestionPaper paper, QuestionGenerateRequest req) {
        String difficulty = req.difficulty() == null || req.difficulty().isBlank() ? "中等" : req.difficulty();

        int totalQ = 0;
        for (QuestionPaper.Section section : paper.sections()) {
            if (section.items() == null) continue;
            totalQ += section.items().size();
        }

        String title = paper.title() == null || paper.title().isBlank()
                ? "AI 生成题目" : paper.title();
        String topic = paper.topic() == null || paper.topic().isBlank() ? "综合复习" : paper.topic();
        String source = req.fileName() == null ? "" : req.fileName();

        return new QuestionPaper(title, topic, difficulty,
                paper.sections(), totalQ, source,
                req.prompt() == null ? "" : req.prompt());
    }

    // ===================== AI 生题：TikZ 配图编译 =====================

    /** ```tikz 围栏代码块（大模型重绘的题目配图源码，由后端编译为图片） */
    private static final Pattern TIKZ_BLOCK = Pattern.compile("```tikz[^\\n]*\\n([\\s\\S]*?)```");

    /**
     * TikZ 节点标签开头的字号词：AI 偶尔把 \small 写漏反斜杠，生成 {smallD_1} / {smallA}，
     * 结果会把字号词当普通文本渲染到图中；编译前去掉这些标签内的字号前缀。
     */
    private static final Pattern NODE_LABEL_LEADING_FONT_WORD =
            Pattern.compile("(node(?:\\[[^\\]]*\\])?(?:\\s+at\\s+\\([^()]*\\))?\\s*\\{)(\\$?)(\\\\?)(small|normalsize|footnotesize|large|Large|LARGE|huge|Huge|tiny|scriptsize)(?:\\s+|(?=[A-Z\\\\$]))([^{}$]*)(\\$?)(\\})");

    /**
     * TikZ 节点标签里的裸下标：如 node[left] {A_1} -- 文本模式下划线是 LaTeX 语法错误
     * （级联报错导致整图编译失败），整体补成 $A_1$ 修复。兼容 node[选项]、node at (坐标) 两种形式。
     */
    private static final Pattern NODE_LABEL_UNDERSCORE =
            Pattern.compile("(node(?:\\[[^\\]]*\\])?(?:\\s+at\\s+\\([^()]*\\))?\\s*\\{)([^{}$]*_[^{}$]*)(\\})");

    /**
     * TikZ every node/.style 里直接写字体命令（如 {\small}）是致命错误：
     * style 的值必须是 key=value 选项列表，裸字体命令会触发无限递归导致 TeX capacity exceeded。
     * 统一改写成 font=\small 形式。支持 \small / \normalsize / \footnotesize / \large 等常见字号。
     */
    private static final Pattern EVERY_NODE_STYLE_FONT =
            Pattern.compile("(every node\\s*/\\s*\\.style\\s*=\\s*\\{)([^}]*)(\\})");

    /**
     * TikZ 行首缺失反斜杠的 node 命令：JSON 字符串里若误写 \node，\n 会先被解析成换行，
     * 进入编译阶段就变成行首 ode[...]；也兼容模型直接漏写反斜杠生成的 node[...]。
     */
    private static final Pattern LINE_START_BARE_NODE_COMMAND =
            Pattern.compile("(?m)^(\\s*)(?:node|ode)(?=\\s*\\[)");

    /**
     * 判断 TikZ 代码是否被做了双重 JSON 转义：AI 输出 JSON 时把 q 字段内的 TikZ 多转义了一层，
     * 导致反斜杠变成 \\（双反斜杠）、换行变成字面 \n 两个字符。
     * 特征：出现 \\begin{tikzpicture} 且包含字面 \n。
     */
    private static boolean isDoubleEscapedTikz(String code) {
        if (code == null) return false;
        return code.contains("\\\\begin{tikzpicture}") && code.contains("\\n");
    }

    /**
     * 对双重转义的 TikZ 做一次反转义：把字面 \n 还原成真换行，把 \\ 还原成 \。
     * 仅在确认双重转义时调用。
     */
    private static String unescapeDoubleEscapedTikz(String code) {
        // 先把字面 \n 替换成真换行（必须先换，否则后面换 \\ 会把 \n 的反斜杠也换掉）
        code = code.replace("\\n", "\n");
        // 再把双反斜杠还原成单反斜杠（TikZ 命令前的 \\ 是多余的一层转义）
        code = code.replace("\\\\", "\\");
        return code;
    }

    /** 编译前的 TikZ 源码修正：误渲染的标签字号词移除、裸下标标签补数学模式包裹、every node 里的字体命令改 font= 等；
     * 已合法的代码不受影响。 */
    private String sanitizeTikz(String code) {
        if (code == null) return code;
        // 先做双重转义检测与修正（AI 把 TikZ 嵌在 JSON 字符串里时偶尔多转义一层）
        if (isDoubleEscapedTikz(code)) {
            code = unescapeDoubleEscapedTikz(code);
        }
        code = LINE_START_BARE_NODE_COMMAND.matcher(code).replaceAll("$1\\\\node");
        code = NODE_LABEL_LEADING_FONT_WORD.matcher(code).replaceAll("$1$2$5$6$7");
        if (code.contains("_")) {
            code = NODE_LABEL_UNDERSCORE.matcher(code).replaceAll("$1\\$$2\\$$3");
        }
        if (code.contains("every node")) {
            code = EVERY_NODE_STYLE_FONT.matcher(code).replaceAll(mr -> {
                String prefix = mr.group(1);
                String body = mr.group(2);
                String suffix = mr.group(3);
                // 规则 1：把裸字号命令改写成 font=... 形式；支持 \small \normalsize \footnotesize \large 等
                String fixed = body.replaceAll(
                        "(^|,)\\s*\\\\(small|normalsize|footnotesize|large|Large|LARGE|huge|Huge|tiny|scriptsize)",
                        "$1font=\\\\$2");
                // 规则 2：font=small 这类漏写反斜杠的，补成 font=\\small
                fixed = fixed.replaceAll(
                        "(^|,|\\s)font\\s*=\\s*(small|normalsize|footnotesize|large|Large|LARGE|huge|Huge|tiny|scriptsize)(?=\\s*(?:,|$))",
                        "$1font=\\\\$2");
                return prefix + fixed + suffix;
            });
        }
        return code;
    }

    /**
     * 把题目里的 ```tikz 代码块编译成配图 PNG（调用 latex_snippet_tool.py，xelatex 编译并裁剪），
     * 保存到题目插图目录，代码块改写为 Markdown 图片链接。
     * 编译失败时保留原代码块（前端等宽展示源码），不阻塞出题主流程。
     */
    private QuestionPaper renderTikzFigures(QuestionPaper paper) {
        if (paper.sections() == null) return paper;
        List<QuestionPaper.Section> sections = paper.sections().stream().map(sec -> {
            if (sec.items() == null) return sec;
            List<QuestionPaper.Item> items = sec.items().stream().map(item -> new QuestionPaper.Item(
                    localizeTikzBlocks(item.q()),
                    item.o() == null ? null : item.o().stream().map(this::localizeTikzBlocks).toList(),
                    localizeTikzBlocks(item.a()),
                    localizeTikzBlocks(item.note()),
                    item.d())).toList();
            return new QuestionPaper.Section(sec.type(), items);
        }).toList();
        return new QuestionPaper(paper.title(), paper.topic(), paper.difficulty(),
                sections, paper.totalQ(), paper.source(), paper.prompt());
    }

    /** 改写一段文本里的 ```tikz 代码块为配图链接；无代码块或编译失败时原样返回 */
    private String localizeTikzBlocks(String text) {
        if (text == null || !text.contains("```tikz")) return text;
        Matcher m = TIKZ_BLOCK.matcher(text);
        StringBuilder sb = new StringBuilder();
        boolean changed = false;
        while (m.find()) {
            String replacement = m.group(0);
            // 裸下标标签等常见语法问题先修正（修正后的源码存回题干，前端编辑器里即合法代码）
            String code = sanitizeTikz(m.group(1).trim());
            TikzResult r = compileTikz(code);
            if (r.ok()) {
                // 统一用正斜杠，与 persistImages 的图片链接写法一致；
                // TikZ 源码随图保留在题干末尾，前端"编辑配图"据此改码重编译
                replacement = "![配图](" + r.path().toString().replace('\\', '/')
                        + ")\n```tikz\n" + code + "\n```";
                changed = true;
            }
            m.appendReplacement(sb, Matcher.quoteReplacement(replacement));
        }
        m.appendTail(sb);
        return changed ? sb.toString() : text;
    }

    /**
     * 单个 TikZ 代码块 -> PNG：{@code python latex_snippet_tool.py --file <tmp.tex> --out <dst.png>}。
     * 子进程模式照搬 LectureValidateService：PYTHONIOENCODING=utf-8 防乱码、
     * redirectErrorStream + redirectOutput 到日志文件防管道死锁。
     */
    private TikzResult compileTikz(String code) {
        Path script = Path.of(tikzScript);
        if (!Files.isRegularFile(script)) {
            log.warn("TikZ 渲染脚本不存在，保留代码块: {}", script);
            return new TikzResult(null, "渲染脚本不存在: " + script);
        }
        Path logFile = null;
        try {
            Path dir = Path.of(questionImageDir);
            Files.createDirectories(dir);
            // 时间戳前缀防多实例/多次运行撞名（IMG_SEQ 仅进程内计数）
            Path dst = dir.resolve("tikz" + System.currentTimeMillis() + "_" + IMG_SEQ.incrementAndGet() + ".png");
            Path tex = Files.createTempFile("tikz_", ".tex");
            logFile = Files.createTempFile("tikz_", ".log");
            Files.writeString(tex, code, StandardCharsets.UTF_8);
            ProcessBuilder pb = new ProcessBuilder(Path.of(tikzPython).toString(), script.toString(),
                            "--file", tex.toString(), "--width", "10", "--out", dst.toString())
                    .redirectErrorStream(true)
                    .redirectOutput(logFile.toFile());
            pb.environment().put("PYTHONIOENCODING", "utf-8");
            Process p = pb.start();
            // 工具内部 xelatex 上限 120s（MiKTeX 后台装包时会慢），外层超时留足余量
            if (!p.waitFor(200, TimeUnit.SECONDS)) {
                p.destroyForcibly();
                log.warn("TikZ 编译超时（>200s），保留代码块");
                return new TikzResult(null, "编译超时（>200s），请检查 TikZ 代码是否过于复杂");
            }
            if (p.exitValue() != 0 || !Files.isRegularFile(dst)) {
                String out = Files.readString(logFile, StandardCharsets.UTF_8);
                log.warn("TikZ 编译失败，保留代码块:\n{}", out);
                return new TikzResult(null, "XeLaTeX 编译失败，请检查 TikZ 代码（括号配对/命令拼写）" + tikzErrorTail(out));
            }
            log.info("TikZ 配图已生成: {}", dst);
            return new TikzResult(dst, null);
        } catch (Exception e) {
            log.warn("TikZ 编译异常，保留代码块: {}", e.getMessage());
            return new TikzResult(null, "编译异常: " + e.getMessage());
        } finally {
            if (logFile != null) {
                try {
                    Files.deleteIfExists(logFile);
                } catch (IOException ignored) {
                }
            }
        }
    }

    /** TikZ 编译结果：成功带生成的 PNG 路径，失败带错误摘要（回传前端编辑器提示） */
    private record TikzResult(Path path, String error) {
        boolean ok() {
            return path != null;
        }
    }

    /**
     * 编译错误摘要：优先取 "!" 开头的 TeX 报错行（附其下一行上下文），没有则取日志末尾几行。
     * 带 "：" 前缀拼在概要后，给前端提示与修正模型看；摘要为空返回空串。
     */
    private static String tikzErrorTail(String log) {
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


    /**
     * 把题目里引用的图片保存到本地目录：远程图片（http/https）下载，本地绝对路径图片拷贝，
     * 题干/选项/答案/解析中的图片链接改写为副本绝对路径（前端经 /seeview/local-image 渲染）。
     * 保存失败时保留原链接，不阻塞出题主流程；codecogs 公式图片链接不做处理（前端还原为 LaTeX）。
     */
    private QuestionPaper persistImages(QuestionPaper paper) {
        if (paper.sections() == null) return paper;
        List<QuestionPaper.Section> sections = paper.sections().stream().map(sec -> {
            if (sec.items() == null) return sec;
            List<QuestionPaper.Item> items = sec.items().stream().map(item -> new QuestionPaper.Item(
                    localizeImageRefs(item.q()),
                    item.o() == null ? null : item.o().stream().map(this::localizeImageRefs).toList(),
                    localizeImageRefs(item.a()),
                    localizeImageRefs(item.note()),
                    item.d())).toList();
            return new QuestionPaper.Section(sec.type(), items);
        }).toList();
        return new QuestionPaper(paper.title(), paper.topic(), paper.difficulty(),
                sections, paper.totalQ(), paper.source(), paper.prompt());
    }

    /** 改写一段文本里的图片链接为本地副本路径；无图片或保存失败时原样返回 */
    private String localizeImageRefs(String text) {
        if (text == null || text.isBlank() || !text.contains("](")) return text;
        Matcher m = MD_IMAGE.matcher(text);
        StringBuilder sb = new StringBuilder();
        boolean changed = false;
        while (m.find()) {
            String replacement = m.group(0);
            Path saved = saveImage(m.group(2).trim());
            if (saved != null) {
                // 统一用正斜杠，前端本地路径识别两种写法，JSON 序列化也无需转义
                replacement = "![" + m.group(1) + "](" + saved.toString().replace('\\', '/') + ")";
                changed = true;
            }
            m.appendReplacement(sb, Matcher.quoteReplacement(replacement));
        }
        m.appendTail(sb);
        return changed ? sb.toString() : text;
    }

    /** 按来源分发：远程下载 / 本地拷贝；其余（相对路径等）返回 null 保留原样 */
    private Path saveImage(String src) {
        if (src == null || src.isBlank()) return null;
        if (REMOTE_IMAGE.matcher(src).matches()) {
            if (CODECOGS_URL.matcher(src).find()) return null;
            return downloadImage(src);
        }
        if (LOCAL_PATH.matcher(src).matches()) {
            return copyImage(src);
        }
        return null;
    }

    /** 下载远程图片；失败（网络/状态码/大小/类型）返回 null */
    private Path downloadImage(String url) {
        try {
            HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                    .timeout(Duration.ofSeconds(20)).GET().build();
            HttpResponse<byte[]> resp = HTTP_CLIENT.send(request, HttpResponse.BodyHandlers.ofByteArray());
            if (resp.statusCode() != 200 || resp.body() == null || resp.body().length == 0) {
                log.warn("题目图片下载失败 status={} url={}", resp.statusCode(), url);
                return null;
            }
            if (resp.body().length > MAX_IMAGE_BYTES) {
                log.warn("题目图片超过 {}B 上限，跳过: {}", MAX_IMAGE_BYTES, url);
                return null;
            }
            String ext = extFromUrl(url);
            if (ext == null) ext = extFromContentType(resp.headers().firstValue("Content-Type").orElse(null));
            if (ext == null) {
                log.warn("题目图片类型无法识别，跳过: {}", url);
                return null;
            }
            return writeImage(resp.body(), ext, nameHintFromUrl(url));
        } catch (Exception e) {
            log.warn("题目图片下载异常，保留原链接: {} -> {}", url, e.getMessage());
            return null;
        }
    }

    /** 拷贝本地绝对路径图片；文件不存在或扩展名不在白名单返回 null */
    private Path copyImage(String path) {
        try {
            Path src = Path.of(path);
            String name = src.getFileName() == null ? "" : src.getFileName().toString();
            int dot = name.lastIndexOf('.');
            String ext = dot > 0 ? name.substring(dot + 1).toLowerCase() : "";
            if (!IMAGE_EXTS.contains(ext) || !Files.isRegularFile(src)) {
                log.warn("题目图片不存在或类型不支持，保留原引用: {}", path);
                return null;
            }
            Path dir = Path.of(questionImageDir);
            Files.createDirectories(dir);
            Path dst = dir.resolve("img" + IMG_SEQ.incrementAndGet() + "_" + safeName(name));
            Files.copy(src, dst, StandardCopyOption.REPLACE_EXISTING);
            log.info("题目图片已拷贝: {} -> {}", path, dst);
            return dst;
        } catch (Exception e) {
            log.warn("题目图片拷贝失败，保留原引用: {} -> {}", path, e.getMessage());
            return null;
        }
    }

    private Path writeImage(byte[] bytes, String ext, String nameHint) throws IOException {
        Path dir = Path.of(questionImageDir);
        Files.createDirectories(dir);
        String safe = safeName(nameHint);
        if (safe.isBlank() || ".".equals(safe)) safe = "image";
        // 提示名已带正确扩展名时不再追加，否则补上
        String fileName = safe.endsWith("." + ext) ? safe : safe + "." + ext;
        Path dst = dir.resolve("img" + IMG_SEQ.incrementAndGet() + "_" + fileName);
        Files.write(dst, bytes);
        log.info("题目图片已下载: {} ({}B)", dst, bytes.length);
        return dst;
    }

    /** 从 URL 取白名单内的图片扩展名（去掉查询串）；识别不了返回 null */
    private String extFromUrl(String url) {
        String path = url;
        int q = path.indexOf('?');
        if (q >= 0) path = path.substring(0, q);
        int slash = Math.max(path.lastIndexOf('/'), path.lastIndexOf('\\'));
        String name = slash >= 0 ? path.substring(slash + 1) : path;
        int dot = name.lastIndexOf('.');
        String ext = dot > 0 ? name.substring(dot + 1).toLowerCase() : "";
        return IMAGE_EXTS.contains(ext) ? ext : null;
    }

    private String extFromContentType(String contentType) {
        if (contentType == null) return null;
        return switch (contentType.toLowerCase().split(";")[0].trim()) {
            case "image/png" -> "png";
            case "image/jpeg" -> "jpg";
            case "image/gif" -> "gif";
            case "image/bmp" -> "bmp";
            case "image/webp" -> "webp";
            case "image/svg+xml" -> "svg";
            default -> null;
        };
    }

    /** 取 URL 最后一段作为文件名提示（去查询串） */
    private String nameHintFromUrl(String url) {
        String path = url;
        int q = path.indexOf('?');
        if (q >= 0) path = path.substring(0, q);
        int slash = Math.max(path.lastIndexOf('/'), path.lastIndexOf('\\'));
        return slash >= 0 ? path.substring(slash + 1) : path;
    }

    /** 文件名里的路径非法字符替换为下划线，保留中文与常用字符（与讲题服务同规则） */
    private String safeName(String name) {
        return name == null ? "" : name.replaceAll("[^\\w.\\-一-龥]", "_");
    }
}
