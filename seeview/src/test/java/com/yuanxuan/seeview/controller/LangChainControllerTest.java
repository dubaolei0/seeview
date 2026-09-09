package com.yuanxuan.seeview.controller;

import com.yuanxuan.seeview.dto.QuestionGenerateRequest;
import com.yuanxuan.seeview.dto.QuestionPaper;
import com.yuanxuan.seeview.dto.TikzFixRequest;
import com.yuanxuan.seeview.service.FigureLibraryService;
import org.apache.poi.util.Units;
import org.apache.poi.xwpf.usermodel.XWPFDocument;
import org.apache.poi.xwpf.usermodel.XWPFParagraph;
import org.apache.poi.xwpf.usermodel.XWPFRun;
import org.apache.poi.xwpf.usermodel.XWPFTable;
import org.apache.xmlbeans.XmlObject;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class LangChainControllerTest {

    private LangChainController controllerWithFigureLibrary() throws Exception {
        LangChainController controller = new LangChainController();
        FigureLibraryService library = new FigureLibraryService(null);
        Path figureDir = Files.isDirectory(Path.of("figure_library"))
                ? Path.of("figure_library")
                : Path.of("..", "figure_library");
        Field libraryDir = FigureLibraryService.class.getDeclaredField("libraryDir");
        libraryDir.setAccessible(true);
        libraryDir.set(library, figureDir.toAbsolutePath().normalize().toString());
        Field figureLibrary = LangChainController.class.getDeclaredField("figureLibrary");
        figureLibrary.setAccessible(true);
        figureLibrary.set(controller, library);
        return controller;
    }

    @Test
    void figureCatalogPromptListsElementsWhenPresent() throws Exception {
        LangChainController controller = controllerWithFigureLibrary();
        Method method = LangChainController.class.getDeclaredMethod("figureCatalogPrompt");
        method.setAccessible(true);

        String catalog = (String) method.invoke(controller);

        // 只要 figure_library 里有任一模板回填了 elements，目录就应输出可画元素行
        // Task 4 会回填 cuboid 模板；若 Task 4 未完成则本测试可能失败——故本测试在 Task 4 后跑
        assertThat(catalog).contains("可画元素：");
    }

    @Test
    void parseIfNumConditionRecognizesTemplateBranches() throws Exception {
        Method method = LangChainController.class.getDeclaredMethod("parseIfNumCondition", String.class);
        method.setAccessible(true);

        Object condition = method.invoke(null, "\\ifnum\\showpoints>0");

        assertThat(condition).isNotNull();
        assertThat(condition.toString()).contains("showpoints").contains(">").contains("0");
        Method eval = condition.getClass().getDeclaredMethod("eval", com.yuanxuan.seeview.dto.FigureTemplate.class, Map.class);
        eval.setAccessible(true);
        LangChainController controller = controllerWithFigureLibrary();
        FigureLibraryService library = (FigureLibraryService) getField(controller, "figureLibrary");
        assertThat((Boolean) eval.invoke(condition,
                library.get("oblique-quadrangular-prism-basic"), Map.of("showpoints", false))).isFalse();
    }

    @Test
    void visibleTemplateLabelsHonorsIfNumBranches() throws Exception {
        LangChainController controller = controllerWithFigureLibrary();
        FigureLibraryService library = (FigureLibraryService) getField(controller, "figureLibrary");
        Method method = LangChainController.class.getDeclaredMethod("visibleTemplateLabels", com.yuanxuan.seeview.dto.FigureTemplate.class, Map.class);
        method.setAccessible(true);

        @SuppressWarnings("unchecked")
        List<String> labels = (List<String>) method.invoke(null,
                library.get("oblique-quadrangular-prism-basic"), Map.of("showpoints", false));

        assertThat(labels).contains("A", "A_1").doesNotContain("E", "F", "G");
    }

    private Object getField(Object target, String name) throws Exception {
        Field field = target.getClass().getDeclaredField(name);
        field.setAccessible(true);
        return field.get(target);
    }

    @Test
    void obliquePrismFigRequiresNamedPrismWhenVertexLabelsVisible() throws Exception {
        LangChainController controller = controllerWithFigureLibrary();
        Method method = LangChainController.class.getDeclaredMethod(
                "validateFigureTextConsistency", String.class, QuestionPaper.FigureRef.class);
        method.setAccessible(true);

        String error = (String) method.invoke(controller,
                "如图，在一个斜四棱柱中，底面边长满足 $AB=3$，求其体积。",
                new QuestionPaper.FigureRef("oblique-quadrangular-prism-basic", Map.of("showverts", true)));

        assertThat(error)
                .contains("题干未写明四棱柱命名")
                .contains("ABCD-A_1B_1C_1D_1");
    }

    @Test
    void obliquePrismFigRequiresAuxiliaryPointDefinitionsWhenPointsVisible() throws Exception {
        LangChainController controller = controllerWithFigureLibrary();
        Method method = LangChainController.class.getDeclaredMethod(
                "validateFigureTextConsistency", String.class, QuestionPaper.FigureRef.class);
        method.setAccessible(true);

        String error = (String) method.invoke(controller,
                "如图，在四棱柱 $ABCD-A_1B_1C_1D_1$ 中，求异面直线所成角。",
                new QuestionPaper.FigureRef("oblique-quadrangular-prism-basic", Map.of("showpoints", true)));

        assertThat(error)
                .contains("图中显示标签 E、F、G")
                .contains("题干未出现这些标签");
    }

    @Test
    void obliquePrismFigAcceptsNamedPrismWithHiddenAuxiliaryPoints() throws Exception {
        LangChainController controller = controllerWithFigureLibrary();
        Method method = LangChainController.class.getDeclaredMethod(
                "validateFigureTextConsistency", String.class, QuestionPaper.FigureRef.class);
        method.setAccessible(true);

        String error = (String) method.invoke(controller,
                "如图，在四棱柱 $ABCD-A_1B_1C_1D_1$ 中，$AB=3$，$AA_1=4$，求其体积。",
                new QuestionPaper.FigureRef("oblique-quadrangular-prism-basic", Map.of("showpoints", false)));

        assertThat(error).isNull();
    }

    @Test
    void circleFigRequiresVisibleCenterLabelInStem() throws Exception {
        LangChainController controller = controllerWithFigureLibrary();
        Method method = LangChainController.class.getDeclaredMethod(
                "validateFigureTextConsistency", String.class, QuestionPaper.FigureRef.class);
        method.setAccessible(true);

        String error = (String) method.invoke(controller,
                "如图，已知圆的半径为 3，求其直径。",
                new QuestionPaper.FigureRef("circle", Map.of("showcenter", true, "showradius", false)));

        assertThat(error)
                .contains("图中显示标签 O")
                .contains("题干未出现这些标签");
    }

    @Test
    void circleFigAcceptsStemWithVisibleLabels() throws Exception {
        LangChainController controller = controllerWithFigureLibrary();
        Method method = LangChainController.class.getDeclaredMethod(
                "validateFigureTextConsistency", String.class, QuestionPaper.FigureRef.class);
        method.setAccessible(true);

        String error = (String) method.invoke(controller,
                "如图，圆 $O$ 的半径 $OA=3$，求其直径。",
                new QuestionPaper.FigureRef("circle", Map.of("showcenter", true, "showradius", true)));

        assertThat(error).isNull();
    }

    @Test
    void questionPromptRequiresVisibleFigureLabelsInStem() throws Exception {
        LangChainController controller = new LangChainController();
        Method method = LangChainController.class.getDeclaredMethod(
                "questionSystemPrompt", QuestionGenerateRequest.class, String.class);
        method.setAccessible(true);

        String prompt = (String) method.invoke(controller, new QuestionGenerateRequest(
                List.of("解答题"), "中等", 1, null, null, "立体几何题", null, "oblique-quadrangular-prism-basic"), "数学");

        assertThat(prompt)
                .contains("凡模板参数会让图中显示某个点名、线名、角名或元件名")
                .contains("该名称必须在题干中明确定义并参与设问")
                .contains("必须关闭对应 show 参数");
    }

    @Test
    void parallelogramFigRequiresStemLineWhenHeightIsShown() throws Exception {
        LangChainController controller = controllerWithFigureLibrary();
        Method method = LangChainController.class.getDeclaredMethod(
                "validateFigureTextConsistency", String.class, QuestionPaper.FigureRef.class);
        method.setAccessible(true);

        String error = (String) method.invoke(controller,
                "如图，在平行四边形 ABCD 中，求 AB 的长度。",
                new QuestionPaper.FigureRef("parallelogram", Map.of(
                        "showheightd", true, "footlabel", "M")));

        assertThat(error)
                .contains("图中显示的线段").contains("DM").contains("题干未出现");
    }

    @Test
    void parallelogramFigAcceptsShownHeightAndNamedFoot() throws Exception {
        LangChainController controller = controllerWithFigureLibrary();
        Method method = LangChainController.class.getDeclaredMethod(
                "validateFigureTextConsistency", String.class, QuestionPaper.FigureRef.class);
        method.setAccessible(true);

        String error = (String) method.invoke(controller,
                "如图，在平行四边形 ABCD 中，过 D 作 DM⊥AB，求 AB 的长度。",
                new QuestionPaper.FigureRef("parallelogram", Map.of(
                        "showheightd", true, "footlabel", "M")));

        assertThat(error).isNull();
    }

    @Test
    void parallelogramFigRejectsStemPointThatTemplateCannotShow() throws Exception {
        LangChainController controller = controllerWithFigureLibrary();
        Method method = LangChainController.class.getDeclaredMethod(
                "validateFigureTextConsistency", String.class, QuestionPaper.FigureRef.class);
        method.setAccessible(true);

        String error = (String) method.invoke(controller,
                "如图，在平行四边形 ABCD 中，点 P 在 AB 上，求 AB 的长度。",
                new QuestionPaper.FigureRef("parallelogram", Map.of()));

        assertThat(error).contains("P").contains("图中没有");
    }

    @Test
    void questionPromptRequiresTikzCoordinatesAndSeparateWhiteLabels() throws Exception {
        LangChainController controller = new LangChainController();
        Method method = LangChainController.class.getDeclaredMethod(
                "questionSystemPrompt", QuestionGenerateRequest.class, String.class);
        method.setAccessible(true);

        String prompt = (String) method.invoke(controller, new QuestionGenerateRequest(
                List.of("解答题"), "中等", 1, null, null, "立体几何题", null, null), "数学");

        assertThat(prompt)
                .contains("默认学段为高中")
                .contains("一律以高中课标为基准")
                .contains("几何顶点必须用 \\coordinate")
                .contains("禁止用 \\node (A) at (...) {A}; 同时承担顶点和标签")
                .contains("所有连线只能连接 coordinate 名称")
                .contains("顶点标签必须单独写成 \\node[below left=2pt, fill=none, inner sep=1pt] at (A) {A};")
                .contains("若一个点有两条以上线段相连，标签必须放在这些线段夹角外侧");
    }

    @Test
    void questionPromptRequiresPyramidHiddenEdgesAndOuterLabels() throws Exception {
        LangChainController controller = new LangChainController();
        Method method = LangChainController.class.getDeclaredMethod(
                "questionSystemPrompt", QuestionGenerateRequest.class, String.class);
        method.setAccessible(true);

        String prompt = (String) method.invoke(controller, new QuestionGenerateRequest(
                List.of("解答题"), "中等", 1, null, null, "立体几何棱锥题", null, null), "数学");

        assertThat(prompt)
                .contains("默认学段为高中")
                .contains("棱锥可见性判定")
                .contains("底面后边、从顶点连到背侧底点且被前方面遮挡的棱必须用 dashed")
                .contains("前轮廓底边、可见侧棱必须用实线")
                .contains("辅助连线也要按空间遮挡判定")
                .contains("位于可见表面或图形外侧的辅助线用实线，被几何体前方面遮挡的辅助线用 dashed")
                .contains("棱锥标签避让模板")
                .contains("边长数字必须写成 node[midway, sloped, above=4pt, fill=none, inner sep=1.5pt]")
                .contains("顶点字母必须放在棱锥外轮廓外侧，偏移量不小于 4pt");
    }

    @Test
    void sanitizeTikzUnescapesDoubleEscapedTikzFromJsonNestedString() throws Exception {
        LangChainController controller = new LangChainController();
        Method method = LangChainController.class.getDeclaredMethod("sanitizeTikz", String.class);
        method.setAccessible(true);

        // AI 把 TikZ 嵌在 JSON 的 q 字段里时偶发双重转义：反斜杠变成 \\、换行变成字面 \n
        String code = "\\\\begin{tikzpicture}[scale=0.85]\\n"
                + "\\\\coordinate (A) at (0,0);\\n"
                + "\\\\draw (A)--(B);\\n"
                + "\\\\node[below left=4pt, fill=none] at (A) {A};\\n"
                + "\\\\end{tikzpicture}";

        String sanitized = (String) method.invoke(controller, code);

        assertThat(sanitized)
                .contains("\\begin{tikzpicture}")
                .contains("\n\\coordinate (A) at (0,0);")
                .contains("\n\\draw (A)--(B);")
                .contains("\\node[below left=4pt, fill=none] at (A) {A};")
                .contains("\\end{tikzpicture}")
                .doesNotContain("\\\\begin")
                .doesNotContain("\\n\\coordinate");
    }

    @Test
    void sanitizeTikzLeavesNormalTikzUntouched() throws Exception {
        LangChainController controller = new LangChainController();
        Method method = LangChainController.class.getDeclaredMethod("sanitizeTikz", String.class);
        method.setAccessible(true);

        // 正常单转义 TikZ 不应该被修改
        String code = """
                \\begin{tikzpicture}
                \\coordinate (A) at (0,0);
                \\draw (A)--(B);
                \\end{tikzpicture}
                """;

        String sanitized = (String) method.invoke(controller, code);
        // 核心命令保留单反斜杠
        assertThat(sanitized).contains("\\begin{tikzpicture}");
        assertThat(sanitized).contains("\\coordinate (A) at (0,0);");
        // 不应该丢失任何内容
        assertThat(sanitized).contains("\\draw (A)--(B);");
    }

    @Test
    void sanitizeTikzRestoresNodeCommandCorruptedByJsonNewlineEscape() throws Exception {
        LangChainController controller = new LangChainController();
        Method method = LangChainController.class.getDeclaredMethod("sanitizeTikz", String.class);
        method.setAccessible(true);

        String code = """
                \\begin{tikzpicture}
                ode[below left=4pt, fill=none, inner sep=1.5pt] at (A) {A};
                node[below=4pt, fill=none, inner sep=1.5pt] at (B) {B};
                \\end{tikzpicture}
                """;

        String sanitized = (String) method.invoke(controller, code);

        assertThat(sanitized)
                .contains("\\node[below left=4pt, fill=none, inner sep=1.5pt] at (A) {A};")
                .contains("\\node[below=4pt, fill=none, inner sep=1.5pt] at (B) {B};")
                .doesNotContain("\node[")
                .doesNotContain("\nnode[");
    }

    @Test
    void sanitizeTikzRemovesLiteralFontWordsFromNodeLabels() throws Exception {
        LangChainController controller = new LangChainController();
        Method method = LangChainController.class.getDeclaredMethod("sanitizeTikz", String.class);
        method.setAccessible(true);

        String code = """
                \\begin{tikzpicture}
                \\node[left] at (D1) {smallD_1};
                \\node[below] at (A) {smallA};
                \\node[right] at (B) {normalsizeB};
                \\end{tikzpicture}
                """;

        String sanitized = (String) method.invoke(controller, code);

        assertThat(sanitized)
                .contains("\\node[left] at (D1) {$D_1$};")
                .contains("\\node[below] at (A) {A};")
                .contains("\\node[right] at (B) {B};")
                .doesNotContain("smallD")
                .doesNotContain("smallA")
                .doesNotContain("normalsizeB");
    }

    @Test
    void extractTikzCodeTakesFencedBlockPlainCodeAndRejectsProse() throws Exception {
        LangChainController controller = new LangChainController();
        Method method = LangChainController.class.getDeclaredMethod("extractTikzCode", String.class);
        method.setAccessible(true);

        // 围栏块 + 前置说明：取块内代码
        String fenced = "已把 A 标签移到左上方。\n```tikz\n\\draw (A)--(B);\n```\n";
        assertThat((String) method.invoke(controller, fenced)).isEqualTo("\\draw (A)--(B);");

        // 无围栏的整体纯代码：视为代码本身
        String plain = "\\begin{tikzpicture}\n\\draw (A)--(B);\n\\end{tikzpicture}";
        assertThat((String) method.invoke(controller, plain)).isEqualTo(plain);

        // 纯文字/其他内容：拒绝
        assertThat((String) method.invoke(controller, "抱歉，我无法修改。")).isNull();
        assertThat((String) method.invoke(controller, "  ")).isNull();
    }

    @Test
    void extractTikzCodeTakesCodeWrittenOnFenceHeaderLine() throws Exception {
        LangChainController controller = new LangChainController();
        Method method = LangChainController.class.getDeclaredMethod("extractTikzCode", String.class);
        method.setAccessible(true);

        // 大模型把整段 TikZ 嵌在 JSON 字符串里时偶尔不换行：代码直接跟在 ```tikz 之后，
        // 真换行只出现在节点标签内部（JSON 的 \n 转义）——旧正则会把代码开头截到首个换行为止
        String onFenceHeaderLine = "```tikz \\begin{tikzpicture} \\node[below=4pt] at (7.4,0) {\nx\nx}; \\end{tikzpicture}```";
        assertThat((String) method.invoke(controller, onFenceHeaderLine))
                .isEqualTo("\\begin{tikzpicture} \\node[below=4pt] at (7.4,0) {\nx\nx}; \\end{tikzpicture}");

        // 完全单行的围栏块（块内没有任何换行）：旧正则完全不匹配
        assertThat((String) method.invoke(controller, "```tikz \\draw (A)--(B);```"))
                .isEqualTo("\\draw (A)--(B);");

        // 围栏头同行附说明文字：说明不吃进代码（与旧正则行为一致）
        assertThat((String) method.invoke(controller, "```tikz 示意图\n\\draw (A);\n```"))
                .isEqualTo("\\draw (A);");
    }

    @Test
    void tikzFixNoteTakesTextBeforeFencedBlock() throws Exception {
        LangChainController controller = new LangChainController();
        Method method = LangChainController.class.getDeclaredMethod("tikzFixNote", String.class);
        method.setAccessible(true);

        assertThat((String) method.invoke(controller, "已修改标签位置。\n```tikz\n\\draw;\n```"))
                .isEqualTo("已修改标签位置。");
        assertThat((String) method.invoke(controller, "```tikz\n\\draw;\n```")).isEmpty();
        assertThat((String) method.invoke(controller, (Object) null)).isEmpty();
    }

    @Test
    void tikzFixUserPromptCarriesStemCodeHistoryAndInstruction() throws Exception {
        LangChainController controller = new LangChainController();
        Method method = LangChainController.class.getDeclaredMethod(
                "tikzFixUserPrompt", TikzFixRequest.class, String.class);
        method.setAccessible(true);

        TikzFixRequest req = new TikzFixRequest(
                "如图，正方体 ABCD-A1B1C1D1 中，AB=2。",
                "\\draw (A)--(B);",
                List.of(
                        new TikzFixRequest.Message("user", "B 点标签压线了"),
                        new TikzFixRequest.Message("assistant", "已把 B 标签移到右上方。"),
                        new TikzFixRequest.Message("user", "再整体放大一些")));

        String prompt = (String) method.invoke(controller, req, "再整体放大一些");

        assertThat(prompt)
                .contains("【题干】")
                .contains("正方体 ABCD-A1B1C1D1")
                .contains("【当前 TikZ 源码】")
                .contains("\\draw (A)--(B);")
                .contains("【对话历史】")
                .contains("用户：B 点标签压线了")
                .contains("助手：已把 B 标签移到右上方。")
                .contains("【本次修改要求】")
                .contains("再整体放大一些");
    }

    @Test
    void tikzFixSystemPromptSharesRulesWithQuestionPrompt() throws Exception {
        LangChainController controller = new LangChainController();
        Method method = LangChainController.class.getDeclaredMethod("tikzFixSystemPrompt", String.class);
        method.setAccessible(true);

        String prompt = (String) method.invoke(controller, "物理");

        assertThat(prompt)
                .contains("TikZ 配图修正专家")
                .contains("几何顶点必须用 \\coordinate")
                .contains("【高中物理】")
                .contains("```tikz 围栏代码块");
    }

    @Test
    void latestUserMessageReturnsLastUserEntry() throws Exception {
        LangChainController controller = new LangChainController();
        Method method = LangChainController.class.getDeclaredMethod("latestUserMessage", List.class);
        method.setAccessible(true);

        List<TikzFixRequest.Message> messages = List.of(
                new TikzFixRequest.Message("user", "第一条"),
                new TikzFixRequest.Message("assistant", "已改"),
                new TikzFixRequest.Message("user", "第二条"),
                new TikzFixRequest.Message("assistant", "又改了"));

        assertThat((String) method.invoke(controller, messages)).isEqualTo("第二条");
        assertThat((String) method.invoke(controller, (Object) null)).isNull();
    }

    @Test
    void tikzErrorTailPrefersTexErrorLines() throws Exception {
        Method m = LangChainController.class.getDeclaredMethod("tikzErrorTail", String.class);
        m.setAccessible(true);

        // 优先取 "!" 报错行及其下一行
        assertThat((String) m.invoke(null, "This is XeTeX\n! Undefined control sequence.\nl.12 \\draww (A)\n[1]\n"))
                .startsWith("：\n! Undefined control sequence.")
                .contains("l.12 \\draww (A)");
        // 无 "!" 行：回退取日志末尾非空行
        assertThat((String) m.invoke(null, "line1\nline2\n\n"))
                .contains("line1").contains("line2");
        assertThat((String) m.invoke(null, "  ")).isEmpty();
    }

    @Test
    void ommlToLatexConvertsFractionScriptsRadicalAndDelimiter() throws Exception {
        LangChainController controller = new LangChainController();
        Method method = LangChainController.class.getDeclaredMethod("ommlToLatex", XmlObject.class);
        method.setAccessible(true);

        // 分式
        assertThat((String) method.invoke(controller, XmlObject.Factory.parse("""
                <m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
                  <m:f><m:num><m:r><m:t>x</m:t></m:r></m:num><m:den><m:r><m:t>2</m:t></m:r></m:den></m:f>
                </m:oMath>""")))
                .isEqualTo("\\frac{x}{2}");

        // 上下标（A_1^2）
        assertThat((String) method.invoke(controller, XmlObject.Factory.parse("""
                <m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
                  <m:sSubSup><m:e><m:r><m:t>A</m:t></m:r></m:e><m:sub><m:r><m:t>1</m:t></m:r></m:sub><m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSubSup>
                </m:oMath>""")))
                .isEqualTo("A_{1}^{2}");

        // 根式（deg 为空 -> 平方根）与 n 次根
        assertThat((String) method.invoke(controller, XmlObject.Factory.parse("""
                <m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
                  <m:rad><m:deg/><m:e><m:r><m:t>x</m:t></m:r></m:e></m:rad>
                </m:oMath>""")))
                .isEqualTo("\\sqrt{x}");
        assertThat((String) method.invoke(controller, XmlObject.Factory.parse("""
                <m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
                  <m:rad><m:deg><m:r><m:t>3</m:t></m:r></m:deg><m:e><m:r><m:t>x</m:t></m:r></m:e></m:rad>
                </m:oMath>""")))
                .isEqualTo("\\sqrt[3]{x}");

        // 定界符：绝对值（begChr/endChr 覆盖默认圆括号）
        assertThat((String) method.invoke(controller, XmlObject.Factory.parse("""
                <m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
                  <m:d><m:dPr><m:begChr m:val="|"/><m:endChr m:val="|"/></m:dPr><m:e><m:r><m:t>x</m:t></m:r></m:e></m:d>
                </m:oMath>""")))
                .isEqualTo("|x|");

        // 求和与向量重音（重音字符用转义拼接，避免源码里不可见组合字符）
        assertThat((String) method.invoke(controller, XmlObject.Factory.parse("""
                <m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
                  <m:nary><m:naryPr><m:chr m:val="∑"/></m:naryPr>
                    <m:sub><m:r><m:t>i=1</m:t></m:r></m:sub><m:sup><m:r><m:t>n</m:t></m:r></m:sup>
                    <m:e><m:r><m:t>i</m:t></m:r></m:e></m:nary>
                </m:oMath>""")))
                .isEqualTo("\\sum_{i=1}^{n}i");
        String acc = "<m:oMath xmlns:m=\"http://schemas.openxmlformats.org/officeDocument/2006/math\">"
                + "<m:acc><m:accPr><m:chr m:val=\"" + '⃗' + "\"/></m:accPr>"
                + "<m:e><m:r><m:t>a</m:t></m:r></m:e></m:acc></m:oMath>";
        assertThat((String) method.invoke(controller, XmlObject.Factory.parse(acc)))
                .isEqualTo("\\vec{a}");
    }

    @Test
    void extractDocxPullsLegacyOleEquationImagesInRunOrder() throws Exception {
        LangChainController controller = new LangChainController();
        Field dir = LangChainController.class.getDeclaredField("questionImageDir");
        dir.setAccessible(true);
        Path tmp = Files.createTempDirectory("see-docx-ole-test");
        dir.set(controller, tmp.toString());

        try (InputStream in = Files.newInputStream(
                Path.of("C:/Users/admin/Desktop/AI生题习题/数学/基础图形.docx"))) {
            Method extract = LangChainController.class.getDeclaredMethod("extractDocxText", InputStream.class);
            extract.setAccessible(true);
            String text = (String) extract.invoke(controller, in);

            assertThat(text)
                    .contains("已知点")
                    .contains("存在点")
                    .contains("(精确到0.1度)");
            assertThat(text.split("!\\[材料图片]\\(", -1).length - 1).isGreaterThanOrEqualTo(3);
            assertThat(text).doesNotContain("暂不支持显示");
        } finally {
            try (var files = Files.list(tmp)) {
                files.forEach(f -> {
                    try {
                        Files.deleteIfExists(f);
                    } catch (Exception ignored) {
                    }
                });
            }
            Files.deleteIfExists(tmp);
        }
    }

    @Test
    void extractDocxPullsTextFormulaTableAndImageInOrder() throws Exception {
        LangChainController controller = new LangChainController();
        // 图片落盘目录指向临时目录，避免污染工作区
        Field dir = LangChainController.class.getDeclaredField("questionImageDir");
        dir.setAccessible(true);
        Path tmp = Files.createTempDirectory("see-docx-test");
        dir.set(controller, tmp.toString());

        try (XWPFDocument doc = new XWPFDocument()) {
            // 段落：文字 + OMML 公式 + 文字 交错
            XWPFParagraph p = doc.createParagraph();
            p.getCTP().set(XmlObject.Factory.parse("""
                    <w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                         xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
                      <w:r><w:t>已知函数 </w:t></w:r>
                      <m:oMath><m:f><m:num><m:r><m:t>x</m:t></m:r></m:num><m:den><m:r><m:t>2</m:t></m:r></m:den></m:f></m:oMath>
                      <w:r><w:t xml:space="preserve">，求其单调区间。</w:t></w:r>
                    </w:p>"""));

            // 内嵌图片：1x1 PNG
            XWPFRun picRun = doc.createParagraph().createRun();
            byte[] png = Base64.getDecoder().decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==");
            picRun.addPicture(new ByteArrayInputStream(png), XWPFDocument.PICTURE_TYPE_PNG,
                    "image1.png", Units.toEMU(10), Units.toEMU(10));

            // 表格
            XWPFTable table = doc.createTable(2, 2);
            table.getRow(0).getCell(0).setText("x");
            table.getRow(0).getCell(1).setText("y");
            table.getRow(1).getCell(0).setText("1");
            table.getRow(1).getCell(1).setText("2");

            ByteArrayOutputStream out = new ByteArrayOutputStream();
            doc.write(out);

            Method extract = LangChainController.class.getDeclaredMethod("extractDocxText", InputStream.class);
            extract.setAccessible(true);
            String text = (String) extract.invoke(controller, new ByteArrayInputStream(out.toByteArray()));

            assertThat(text)
                    .contains("已知函数")
                    .contains("$\\frac{x}{2}$")
                    .contains("求其单调区间。")
                    .contains("![材料图片](")
                    .contains(".png)")
                    .contains("| x | y |")
                    .contains("| --- | --- |")
                    .contains("| 1 | 2 |");
            // 段落、图片、表格按文档顺序输出
            assertThat(text.indexOf("已知函数"))
                    .isLessThan(text.indexOf("![材料图片]"))
                    .isLessThan(text.indexOf("| x | y |"));
            // 图片已落盘到临时目录
            try (var files = Files.list(tmp)) {
                assertThat(files.anyMatch(f -> f.getFileName().toString().endsWith(".png"))).isTrue();
            }
        } finally {
            // 清理临时图片
            try (var files = Files.list(tmp)) {
                files.forEach(f -> {
                    try {
                        Files.deleteIfExists(f);
                    } catch (Exception ignored) {
                        // 清理失败不影响断言
                    }
                });
            }
            Files.deleteIfExists(tmp);
        }
    }

    @Test
    void parsePaperNormalizesLiteralNewlineEscapesFromNestedJson() throws Exception {
        LangChainController controller = new LangChainController();
        Method method = LangChainController.class.getDeclaredMethod("parsePaper", String.class);
        method.setAccessible(true);

        // OpenAI HTTP body 里 content 是外层 JSON 字符串；模型又在题干 JSON 字符串里输出 \\n 时，
        // 进入 parsePaper 后会变成题干里的字面 \n，必须还原成真换行，TikZ 围栏才能被识别。
        String raw = """
                {
                  "title": "测试卷",
                  "topic": "棱锥",
                  "sections": [
                    {
                      "type": "解答题",
                      "items": [
                        {
                          "q": "如图，求：\\\\n（1）高；\\\\n```tikz\\\\n\\\\begin{tikzpicture}\\\\n\\\\coordinate (A) at (0,0);\\\\n\\\\draw (A)--(B);\\\\n\\\\end{tikzpicture}\\\\n```",
                          "a": "答",
                          "note": "析",
                          "d": "中等"
                        }
                      ]
                    }
                  ]
                }
                """;

        QuestionPaper paper = (QuestionPaper) method.invoke(controller, raw);
        String q = paper.sections().getFirst().items().getFirst().q();

        assertThat(q)
                .contains("求：\n（1）高；")
                .contains("```tikz\n\\begin{tikzpicture}")
                .doesNotContain("\\n");
    }
}
