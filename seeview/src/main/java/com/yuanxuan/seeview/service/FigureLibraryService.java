package com.yuanxuan.seeview.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.yuanxuan.seeview.dto.FigureTemplate;
import com.yuanxuan.seeview.dto.FigureTemplate.Param;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * 图库 Service：模板加载/保存/删除 + 参数校验 + 模板渲染。
 *
 * <p>存储：{@code figure-library-dir}/figures/*.json，一模板一文件。
 * 渲染流程：参数校验（类型/范围/白名单/约束表达式）-> 生成 {@code \def\参数名{值}} 声明区
 * 拼在模板体之前 -> {@link TikzCompiler} 编译为 PNG。
 *
 * <p>模板体自身不含参数值（只有注释样例），坐标全部由 {\@code \pgfmathsetmacro}
 * 从参数算出，保证数量关系与题干一致。
 */
@Service
public class FigureLibraryService {

    private static final Logger log = LoggerFactory.getLogger(FigureLibraryService.class);

    @Value("${figure.library-dir:${user.dir}/figure_library}")
    private String libraryDir;

    private final TikzCompiler tikzCompiler;


    /** 忽略未知字段（模板 JSON 由人/AI 起草，字段演进时不至于整库加载失败） */
    private final ObjectMapper mapper = new ObjectMapper()
            .configure(com.fasterxml.jackson.databind.DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);

    /** 参数名即 \def 命令名，限小写字母开头的小写字母数字串（防 TeX 注入） */
    private static final Pattern PARAM_NAME = Pattern.compile("^[a-z][a-z0-9]{0,30}$");
    /** 模板 id 限小写字母数字连字符（作文件名） */
    private static final Pattern TEMPLATE_ID = Pattern.compile("^[a-z0-9][a-z0-9-]{0,60}$");
    /** 数值参数合法格式（含小数；分数/表达式不支持，由前端/模型先换算） */
    private static final Pattern NUMBER_VALUE = Pattern.compile("-?\\d+(\\.\\d+)?");

    public FigureLibraryService(TikzCompiler tikzCompiler) {
        this.tikzCompiler = tikzCompiler;
    }

    // ===================== 模板 CRUD =====================

    /** 全部模板目录（id/name/category/tags/desc/params，不含 template 大字段） */
    public synchronized List<FigureTemplate.Catalog> list() {
        List<FigureTemplate.Catalog> out = new ArrayList<>();
        for (Path f : figureFiles()) {
            try {
                FigureTemplate t = readTemplate(f);
                if (t != null) {
                    out.add(new FigureTemplate.Catalog(t.id(), t.name(), t.category(), t.parent(),
                            t.tags(), t.desc(), t.whenNotToUse(), t.params()));
                }
            } catch (Exception e) {
                log.warn("图库模板加载失败，跳过: {} -> {}", f, e.getMessage());
            }
        }
        // 排序：分类 -> 分类内 DFS（顶级模板按名称排，其专用变体紧随其后，保证层级连续）
        java.util.Map<String, String> parentOf = new java.util.HashMap<>();
        for (FigureTemplate.Catalog c : out) parentOf.put(c.id(), c.parent());
        java.util.Map<String, java.util.List<FigureTemplate.Catalog>> kidsOf = new java.util.HashMap<>();
        for (FigureTemplate.Catalog c : out) {
            if (c.parent() != null && !c.parent().isBlank() && parentOf.containsKey(c.parent())) {
                kidsOf.computeIfAbsent(c.parent(), k -> new ArrayList<>()).add(c);
            }
        }
        java.util.Map<String, Integer> order = new java.util.HashMap<>();
        for (java.util.List<FigureTemplate.Catalog> kids : kidsOf.values()) {
            kids.sort((a, b) -> String.valueOf(a.name()).compareTo(String.valueOf(b.name())));
        }
        for (FigureTemplate.Catalog c : out) {
            if (c.parent() != null && parentOf.containsKey(c.parent())) continue; // 只从顶级出发
            java.util.Deque<FigureTemplate.Catalog> stack = new java.util.ArrayDeque<>();
            stack.push(c);
            while (!stack.isEmpty()) {
                FigureTemplate.Catalog cur = stack.pop();
                order.putIfAbsent(cur.id(), order.size());
                java.util.List<FigureTemplate.Catalog> kids = kidsOf.getOrDefault(cur.id(), List.of());
                for (int i = kids.size() - 1; i >= 0; i--) stack.push(kids.get(i)); // 倒序入栈保持正序出栈
            }
        }
        // 父模板不存在/环上的残余模板（理论上被校验挡住，防御性兜底）排到最后
        for (FigureTemplate.Catalog c : out) order.putIfAbsent(c.id(), Integer.MAX_VALUE);
        out.sort((a, b) -> {
            int c = String.valueOf(a.category()).compareTo(String.valueOf(b.category()));
            if (c != 0) return c;
            int o = Integer.compare(order.get(a.id()), order.get(b.id()));
            if (o != 0) return o;
            return String.valueOf(a.name()).compareTo(String.valueOf(b.name()));
        });
        return out;
    }

    /** 按 id 取完整模板；不存在返回 null */
    public synchronized FigureTemplate get(String id) {
        Path f = figureFile(id);
        if (!Files.isRegularFile(f)) return null;
        try {
            return readTemplate(f);
        } catch (Exception e) {
            log.warn("图库模板加载失败: {} -> {}", f, e.getMessage());
            return null;
        }
    }

    /**
     * 保存模板（新建或更新）：校验结构 -> 默认参数试编译（编译不过拒绝入库）-> 落盘。
     *
     * @return 成功返回落盘后的模板（试编译的 PNG 路径丢弃，前端保存后自渲染预览）
     * @throws IllegalArgumentException 结构/参数/编译问题，message 面向用户
     */
    public synchronized FigureTemplate save(FigureTemplate t) {
        validateTemplate(t);
        // 默认参数试编译：保证入库模板在默认参数下一定能出图
        StringBuilder defs = new StringBuilder();
        String err = appendDefs(defs, t, null);
        if (err != null) {
            throw new IllegalArgumentException("默认参数不合法：" + err);
        }
        TikzCompiler.Result r = tikzCompiler.compile(defs + "\n" + t.template().strip());
        if (!r.ok()) {
            throw new IllegalArgumentException("默认参数下模板编译失败，请先修正代码：" + r.error());
        }
        try {
            Path f = figureFile(t.id());
            Files.createDirectories(f.getParent());
            Files.writeString(f, mapper.writerWithDefaultPrettyPrinter().writeValueAsString(t),
                    StandardCharsets.UTF_8);
            log.info("图库模板已保存: {}", f);
            return t;
        } catch (IOException e) {
            throw new IllegalStateException("模板写入失败: " + e.getMessage(), e);
        }
    }

    /** 删除模板；不存在返回 false */
    public synchronized boolean delete(String id) {
        if (id == null) return false;
        Path f = figureFile(id);
        try {
            return Files.deleteIfExists(f);
        } catch (IOException e) {
            throw new IllegalStateException("模板删除失败: " + e.getMessage(), e);
        }
    }

    // ===================== 渲染 =====================

    /**
     * 渲染模板：参数校验 -> \def 注入 -> 编译。
     *
     * @param id     模板 id
     * @param params 参数值（缺省项用默认值）
     * @return 成功带 PNG 路径；失败带错误摘要
     */
    public RenderResult render(String id, Map<String, Object> params) {
        FigureTemplate t = get(id);
        if (t == null) {
            return new RenderResult(null, "图库中不存在模板: " + id);
        }
        StringBuilder defs = new StringBuilder();
        String err = appendDefs(defs, t, params);
        if (err != null) {
            return new RenderResult(null, err);
        }
        TikzCompiler.Result r = tikzCompiler.compile(defs + "\n" + t.template().strip());
        if (!r.ok()) {
            return new RenderResult(null, r.error());
        }
        return new RenderResult(r.path(), null);
    }

    /**
     * 渲染草稿模板（图库编辑器实时预览用）：不落盘，直接按传入的模板定义与参数渲染。
     * 校验口径与 {@link #render} 一致；模板体结构不校验（编辑中允许半成品），只做编译。
     *
     * @param t      编辑中的模板定义（params/template 为当前编辑值）
     * @param params 参数值（缺省补默认值）
     * @return 成功带 PNG 路径；失败带错误摘要
     */
    public RenderResult renderDraft(FigureTemplate t, Map<String, Object> params) {
        if (t == null || t.template() == null || t.template().isBlank()) {
            return new RenderResult(null, "模板代码不能为空");
        }
        if (t.params() == null) {
            return new RenderResult(null, "参数表不能为空");
        }
        StringBuilder defs = new StringBuilder();
        String err = appendDefs(defs, t, params);
        if (err != null) {
            return new RenderResult(null, err);
        }
        TikzCompiler.Result r = tikzCompiler.compile(defs + "\n" + t.template().strip());
        if (!r.ok()) {
            return new RenderResult(null, r.error());
        }
        return new RenderResult(r.path(), null);
    }

    /** 渲染结果：成功带 PNG 路径，失败带面向用户的错误摘要 */
    public record RenderResult(Path path, String error) {
    }

    // ===================== 参数校验与 \def 注入 =====================

    /**
     * 把参数值转成 {\@code \def\name{value}} 声明区追加到 defs（模板体之前）。
     * 缺省参数补默认值；全部校验通过返回 null，否则返回第一个错误的中文描述。
     *
     * <p>值格式：number 原样输出（已用 NUMBER_VALUE 限定）；bool 转 1/0；
     * string 必须在 options 白名单内（白名单本身在 validateTemplate 校验字符安全）。
     */
    private String appendDefs(StringBuilder defs, FigureTemplate t, Map<String, Object> params) {
        Map<String, Object> given = params == null ? Map.of() : params;
        for (Param p : t.params()) {
            Object raw = given.get(p.name());
            if (raw == null || (raw instanceof String s && s.isBlank())) {
                raw = p.def();
            }
            if (raw == null) {
                return "参数 " + FigureLibraryService.paramLabel(p) + " 未提供且无默认值";
            }
            String value = String.valueOf(raw).strip();
            String type = p.type() == null ? "number" : p.type();
            String formatted;
            switch (type) {
                case "number" -> {
                    if (!NUMBER_VALUE.matcher(value).matches()) {
                        return "参数 " + FigureLibraryService.paramLabel(p) + " 需要数字，收到：" + value;
                    }
                    double v = Double.parseDouble(value);
                    if (p.min() != null && v < p.min()) {
                        return "参数 " + FigureLibraryService.paramLabel(p) + "=" + value + " 低于下限 " + num(p.min());
                    }
                    if (p.max() != null && v > p.max()) {
                        return "参数 " + FigureLibraryService.paramLabel(p) + "=" + value + " 超过上限 " + num(p.max());
                    }
                    formatted = value;
                }
                case "bool" -> {
                    // 前端 checkbox / 模型 true/false 都接受，TikZ 侧按 1/0 判断
                    if ("true".equalsIgnoreCase(value) || "1".equals(value)) {
                        formatted = "1";
                    } else if ("false".equalsIgnoreCase(value) || "0".equals(value)) {
                        formatted = "0";
                    } else {
                        return "参数 " + FigureLibraryService.paramLabel(p) + " 需要 true/false，收到：" + value;
                    }
                }
                case "string" -> {
                    if (p.options() == null || !p.options().contains(value)) {
                        return "参数 " + FigureLibraryService.paramLabel(p) + " 取值必须是 "
                                + (p.options() == null ? "未配置白名单" : String.join("/", p.options()))
                                + "，收到：" + value;
                    }
                    formatted = value;
                }
                default -> {
                    return "参数 " + p.name() + " 类型不支持：" + type;
                }
            }
            defs.append("\\def\\").append(p.name()).append('{').append(formatted).append("}\n");
        }
        // 约束表达式校验（如 "ab + bc < 20"）：值全部合法后才求值
        if (t.constraints() != null && !t.constraints().isEmpty()) {
            Map<String, Double> numbers = new java.util.HashMap<>();
            for (Param p : t.params()) {
                String type = p.type() == null ? "number" : p.type();
                if (!"number".equals(type)) continue; // 约束只支持数值参数
                Object raw = given.get(p.name());
                if (raw == null || (raw instanceof String s && s.isBlank())) raw = p.def();
                numbers.put(p.name(), Double.parseDouble(String.valueOf(raw)));
            }
            for (String expr : t.constraints()) {
                String err = checkConstraint(expr, numbers);
                if (err != null) {
                    return err;
                }
            }
        }
        return null;
    }

    /**
     * 求值一条约束表达式：参数名/数字与 + - * / ( ) < <= > >= = 组成的中缀式，结果须为真。
     * 用双栈（Dijkstra shunting yard）求值，不引依赖；解析失败视为约束不满足（保守拒绝）。
     *
     * @return 通过返回 null，否则返回中文错误描述
     */
    private String checkConstraint(String expr, Map<String, Double> numbers) {
        Boolean ok = new ExprEval(expr, numbers).eval();
        if (ok == null) {
            log.warn("约束表达式解析失败: {}", expr);
            return "约束表达式无法求值：" + expr;
        }
        return ok ? null : "参数组合违反约束：" + expr;
    }

    /** 保存前的模板结构校验：id/name/desc/params/template 齐备且格式合法 */
    private void validateTemplate(FigureTemplate t) {
        if (t == null) throw new IllegalArgumentException("模板不能为空");
        if (t.id() == null || !TEMPLATE_ID.matcher(t.id()).matches()) {
            throw new IllegalArgumentException("id 必须是小写字母/数字/连字符（作文件名）");
        }
        if (t.name() == null || t.name().isBlank()) {
            throw new IllegalArgumentException("name 不能为空");
        }
        // 上级模板可选：须是图库中已存在的其他模板，且父链不能成环（自己是自己的祖先）
        if (t.parent() != null && !t.parent().isBlank()) {
            if (t.parent().equals(t.id())) {
                throw new IllegalArgumentException("parent 不能指向自己");
            }
            if (!TEMPLATE_ID.matcher(t.parent()).matches()) {
                throw new IllegalArgumentException("parent 须是模板 id（小写字母/数字/连字符）");
            }
            FigureTemplate p = get(t.parent());
            if (p == null) {
                throw new IllegalArgumentException("上级模板不存在: " + t.parent());
            }
            // 沿父链上溯，出现自己即成环
            java.util.Set<String> seen = new java.util.HashSet<>();
            String cur = p.id();
            while (cur != null && seen.add(cur)) {
                if (cur.equals(t.id())) {
                    throw new IllegalArgumentException("parent 链成环: " + t.parent());
                }
                FigureTemplate next = get(cur);
                cur = next == null ? null : (next.parent() == null || next.parent().isBlank() ? null : next.parent());
            }
        }
        // desc 是模型选图与检索的依据，质量直接决定匹配率，强制具体
        if (t.desc() == null || t.desc().strip().length() < 20) {
            throw new IllegalArgumentException("desc 必填且不少于 20 字（写清什么题适合用这个模板）");
        }
        if (t.params() == null || t.params().isEmpty()) {
            throw new IllegalArgumentException("params 不能为空（无参数图形建议直接用自由 TikZ）");
        }
        for (Param p : t.params()) {
            if (p.name() == null || !PARAM_NAME.matcher(p.name()).matches()) {
                throw new IllegalArgumentException("参数名 " + p.name() + " 不合法（小写字母开头，限小写字母数字）");
            }
            String type = p.type() == null ? "number" : p.type();
            switch (type) {
                case "number" -> {
                    if (p.def() == null || !NUMBER_VALUE.matcher(p.def()).matches()) {
                        throw new IllegalArgumentException("参数 " + p.name() + " 默认值需为数字");
                    }
                }
                case "bool" -> {
                    if (p.def() == null || !("true".equalsIgnoreCase(p.def()) || "false".equalsIgnoreCase(p.def())
                            || "0".equals(p.def()) || "1".equals(p.def()))) {
                        throw new IllegalArgumentException("参数 " + p.name() + " 默认值需为 true/false");
                    }
                }
                case "string" -> {
                    if (p.options() == null || p.options().isEmpty()) {
                        throw new IllegalArgumentException("string 参数 " + p.name() + " 必须配置 options 白名单");
                    }
                    // 白名单进 \def：只允许字母数字与连字符，防 TeX 注入
                    for (String o : p.options()) {
                        if (o == null || !o.matches("[A-Za-z0-9-]{1,30}")) {
                            throw new IllegalArgumentException("string 参数 " + p.name()
                                    + " 的选项须为字母数字连字符：" + o);
                        }
                    }
                    if (p.def() == null || !p.options().contains(p.def())) {
                        throw new IllegalArgumentException("string 参数 " + p.name() + " 默认值不在 options 内");
                    }
                }
                default -> throw new IllegalArgumentException("参数 " + p.name() + " 类型不支持：" + type);
            }
        }
        if (t.template() == null || !t.template().contains("\\begin{tikzpicture}")) {
            throw new IllegalArgumentException("template 必须含 \\begin{tikzpicture}...");
        }
        // 模板体不能自带 \def：参数声明区由后端生成拼上，自带会与注入区冲突
        // （只查非注释行：模板常带 % 注释样例说明参数来源，允许出现）
        String codeLines = t.template().lines()
                .filter(l -> !l.strip().startsWith("%"))
                .collect(java.util.stream.Collectors.joining("\n"));
        if (codeLines.contains("\\def")) {
            throw new IllegalArgumentException("模板体不要写 \\def（参数声明区由系统按参数值自动生成）");
        }
        // 约束表达式引用的参数必须存在（解析失败会在求值时保守拒绝，这里先挡明显笔误）
        if (t.constraints() != null) {
            for (String c : t.constraints()) {
                String err = checkConstraintNames(c, t);
                if (err != null) throw new IllegalArgumentException(err);
            }
        }
    }

    /** 约束表达式里出现的标识符必须是已定义参数名（纯数字是常量，跳过） */
    private String checkConstraintNames(String expr, FigureTemplate t) {
        java.util.Set<String> names = new java.util.HashSet<>();
        for (Param p : t.params()) names.add(p.name());
        for (String tok : expr.split("[^A-Za-z0-9.]+")) {
            if (tok.isBlank() || tok.matches("\\d+(\\.\\d+)?")) continue;
            if (!names.contains(tok)) {
                return "约束表达式引用了未定义的参数：" + tok;
            }
        }
        return null;
    }

    private static String num(double d) {
        return d == Math.floor(d) ? String.valueOf((long) d) : String.valueOf(d);
    }

    // ===================== 文件读写 =====================

    private Path libraryDir() {
        return Path.of(libraryDir);
    }

    private Path figuresDir() {
        return libraryDir().resolve("figures");
    }

    private Path figureFile(String id) {
        return figuresDir().resolve(id + ".json");
    }

    private List<Path> figureFiles() {
        try {
            if (!Files.isDirectory(figuresDir())) return List.of();
            try (var stream = Files.list(figuresDir())) {
                return stream.filter(f -> f.getFileName().toString().endsWith(".json")).toList();
            }
        } catch (IOException e) {
            log.warn("图库目录读取失败: {}", e.getMessage());
            return List.of();
        }
    }

    private FigureTemplate readTemplate(Path f) throws IOException {
        FigureTemplate t = mapper.readValue(Files.readString(f, StandardCharsets.UTF_8), FigureTemplate.class);
        return (t == null || t.id() == null) ? null : t;
    }

    // ===================== 约束表达式求值器（双栈） =====================

    /**
     * 迷你中缀表达式求值：操作数为参数名/数字，运算符 + - * / 与比较
     * &lt; &lt;= &gt; &gt;= =，支持括号。比较结果可再参与 * /（乘法即逻辑与）。
     * 解析失败返回 null（调用方按约束不满足处理，保守拒绝）。
     */
    static final class ExprEval {
        private final String src;
        private final Map<String, Double> vars;
        private int pos;

        ExprEval(String src, Map<String, Double> vars) {
            this.src = src == null ? "" : src;
            this.vars = vars;
        }

        /** 求值成功返回布尔结果；解析失败返回 null */
        Boolean eval() {
            Double v = parseCompare();
            if (v == null || pos < src.length()) return null;
            return v != 0.0;
        }

        private Double parseCompare() {
            Double left = parseAdd();
            if (left == null) return null;
            skipSpace();
            String op = peekOp("<=", ">=", "<", ">", "=");
            if (op == null) return left;
            pos += op.length();
            Double right = parseAdd();
            if (right == null) return null;
            return switch (op) {
                case "<" -> bl(left < right);
                case "<=" -> bl(left <= right);
                case ">" -> bl(left > right);
                case ">=" -> bl(left >= right);
                default -> bl(Math.abs(left - right) < 1e-9);
            };
        }

        private Double parseAdd() {
            Double v = parseMul();
            while (v != null) {
                skipSpace();
                char c = peek();
                if (c != '+' && c != '-') return v;
                pos++;
                Double r = parseMul();
                if (r == null) return null;
                v = c == '+' ? v + r : v - r;
            }
            return null;
        }

        private Double parseMul() {
            Double v = parseUnary();
            while (v != null) {
                skipSpace();
                char c = peek();
                if (c != '*' && c != '/') return v;
                pos++;
                Double r = parseUnary();
                if (r == null) return null;
                if (c == '/' && r == 0.0) return null;
                v = c == '*' ? v * r : v / r;
            }
            return null;
        }

        private Double parseUnary() {
            skipSpace();
            char c = peek();
            if (c == '-') {
                pos++;
                Double v = parseUnary();
                return v == null ? null : -v;
            }
            if (c == '(') {
                pos++;
                Double v = parseCompare();
                skipSpace();
                if (v == null || peek() != ')') return null;
                pos++;
                return v;
            }
            return parseOperand();
        }

        private Double parseOperand() {
            skipSpace();
            int start = pos;
            while (pos < src.length() && (Character.isLetterOrDigit(src.charAt(pos)) || src.charAt(pos) == '.')) {
                pos++;
            }
            if (pos == start) return null;
            String tok = src.substring(start, pos);
            if (tok.matches("-?\\d+(\\.\\d+)?")) return Double.parseDouble(tok);
            Double v = vars.get(tok);
            return v;
        }

        private void skipSpace() {
            while (pos < src.length() && Character.isWhitespace(src.charAt(pos))) pos++;
        }

        private char peek() {
            return pos < src.length() ? src.charAt(pos) : '\0';
        }

        private String peekOp(String... ops) {
            for (String op : ops) {
                if (src.startsWith(op, pos)) return op;
            }
            return null;
        }

        private static Double bl(boolean b) {
            return b ? 1.0 : 0.0;
        }
    }

    // 供 Param.desc 兜底：desc 字段缺失时用参数名
    static String paramLabel(Param p) {
        return p != null && p.desc() != null && !p.desc().isBlank() ? p.desc() : p.name();
    }
}
