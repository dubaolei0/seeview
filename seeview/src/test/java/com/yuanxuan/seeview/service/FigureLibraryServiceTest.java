package com.yuanxuan.seeview.service;

import com.yuanxuan.seeview.dto.FigureTemplate;
import org.junit.jupiter.api.Test;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import static org.assertj.core.api.Assertions.assertThat;

class FigureLibraryServiceTest {

    @Test
    void renderDraftKeepsRenderedPngAsIs() throws Exception {
        Path tmp = Files.createTempDirectory("figure-normalize-test");
        Path compiled = tmp.resolve("compiled.png");
        ImageIO.write(new BufferedImage(800, 200, BufferedImage.TYPE_INT_ARGB), "png", compiled.toFile());

        FigureLibraryService service = new FigureLibraryService(new StaticTikzCompiler(compiled));
        FigureTemplate template = new FigureTemplate(
                "wide-test",
                "宽图测试",
                "测试",
                null,
                List.of("测试"),
                "用于测试图库渲染直接保留原始 PNG 尺寸。",
                null,
                List.of(new FigureTemplate.Param("w", "number", null, null, null, "1", "宽度")),
                null,
                "\\begin{tikzpicture}\n\\draw (0,0)--(1,0);\n\\end{tikzpicture}",
                null   // elements
        );

        FigureLibraryService.RenderResult result = service.renderDraft(template, null);

        assertThat(result.error()).isNull();
        BufferedImage rendered = ImageIO.read(result.path().toFile());
        assertThat(rendered.getWidth()).isEqualTo(800);
        assertThat(rendered.getHeight()).isEqualTo(200);
    }

    @Test
    void renderDraftKeepsTallRenderedPngAsIs() throws Exception {
        Path tmp = Files.createTempDirectory("figure-normalize-tall-test");
        Path compiled = tmp.resolve("compiled.png");
        ImageIO.write(new BufferedImage(100, 400, BufferedImage.TYPE_INT_ARGB), "png", compiled.toFile());

        FigureLibraryService service = new FigureLibraryService(new StaticTikzCompiler(compiled));
        FigureLibraryService.RenderResult result = service.renderDraft(testTemplate(), null);

        assertThat(result.error()).isNull();
        BufferedImage rendered = ImageIO.read(result.path().toFile());
        assertThat(rendered.getWidth()).isEqualTo(100);
        assertThat(rendered.getHeight()).isEqualTo(400);
    }

    @Test
    void renderDraftKeepsTikzPictureOptionsUnchanged() throws Exception {
        // coordScale 已移除：模板体的 tikzpicture 选项应原样进入编译，不再注入 x=cm,y=cm
        RecordingTikzCompiler compiler = new RecordingTikzCompiler();
        FigureLibraryService service = new FigureLibraryService(compiler);
        FigureTemplate template = new FigureTemplate(
                "scale-test",
                "坐标尺度测试",
                "测试",
                null,
                List.of("测试"),
                "用于测试模板体的 tikzpicture 选项原样进入编译。",
                null,
                List.of(new FigureTemplate.Param("w", "number", null, null, null, "1", "宽度")),
                null,
                "\\begin{tikzpicture}[scale=1, every node/.style={font=\\small, fill=none}]\n\\draw (0,0)--(2,0);\n\\end{tikzpicture}",
                null   // elements
        );

        FigureLibraryService.RenderResult result = service.renderDraft(template, null);

        assertThat(result.error()).isNull();
        assertThat(compiler.lastCode).contains("\\begin{tikzpicture}[scale=1, every node/.style={font=\\small, fill=none}]");
    }

    @Test
    void libraryTemplatesAllLoadAndParentChainIntact() throws Exception {
        // 图库目录：兼容从模块目录（mvnw test）与项目根（IDEA）两种工作目录
        Path lib = Path.of("figure_library");
        if (!Files.isDirectory(lib)) lib = Path.of("..", "figure_library");
        assertThat(Files.isDirectory(lib)).as("图库目录存在").isTrue();

        FigureLibraryService service = new FigureLibraryService(new StaticTikzCompiler(Path.of("dummy.png")));
        Field dir = FigureLibraryService.class.getDeclaredField("libraryDir");
        dir.setAccessible(true);
        dir.set(service, lib.toAbsolutePath().toString());

        List<FigureTemplate.Catalog> catalog = service.list();
        // 四边形家族（父模板 + 7 个专用变体）必须全部加载成功；
        // constraints 写成对象数组等格式错误会让 list() 静默跳过，这里兜底发现
        assertThat(catalog).extracting(FigureTemplate.Catalog::id).contains(
                "general-quadrilateral", "parallelogram", "rhombus", "rectangle",
                "square", "trapezoid", "irregular-quadrilateral", "cyclic-quadrilateral");

        // parent 必须指向已加载的模板（悬空 parent 会破坏层级排序）
        Set<String> ids = catalog.stream().map(FigureTemplate.Catalog::id).collect(Collectors.toSet());
        for (FigureTemplate.Catalog c : catalog) {
            if (c.parent() != null && !c.parent().isBlank()) {
                assertThat(ids).as("模板 %s 的 parent %s 应存在于图库", c.id(), c.parent()).contains(c.parent());
            }
        }
    }

    @Test
    void quadrilateralConstraintExpressionsEvaluate() throws Exception {
        // trapezoid / cyclic-quadrilateral 的约束表达式须能被内置求值器解析
        FigureLibraryService service = new FigureLibraryService(new StaticTikzCompiler(Path.of("dummy.png")));
        Method m = FigureLibraryService.class.getDeclaredMethod("checkConstraint", String.class, Map.class);
        m.setAccessible(true);

        Map<String, Double> trap = Map.of("ab", 6.0, "topbase", 3.0, "dx", 1.5);
        assertThat((String) m.invoke(service, "topbase < ab", trap)).isNull();
        assertThat((String) m.invoke(service, "dx >= 0", trap)).isNull();
        assertThat((String) m.invoke(service, "dx + topbase <= ab", trap)).isNull();
        Map<String, Double> trapBad = Map.of("ab", 3.0, "topbase", 5.0, "dx", 1.5);
        assertThat((String) m.invoke(service, "topbase < ab", trapBad)).isNotNull();
        Map<String, Double> trapOver = Map.of("ab", 6.0, "topbase", 3.0, "dx", 4.5);
        assertThat((String) m.invoke(service, "dx + topbase <= ab", trapOver)).isNotNull();

        Map<String, Double> cyc = Map.of("anga", 30.0, "angb", 120.0, "angc", 220.0, "angd", 310.0);
        for (String expr : List.of("angb - anga > 10", "angc - angb > 10",
                "angd - angc > 10", "360 - angd + anga > 10")) {
            assertThat((String) m.invoke(service, expr, cyc)).as("约束 %s 应满足", expr).isNull();
        }
        Map<String, Double> cycBad = Map.of("anga", 30.0, "angb", 35.0, "angc", 220.0, "angd", 310.0);
        assertThat((String) m.invoke(service, "angb - anga > 10", cycBad)).isNotNull();
    }

    private static FigureTemplate testTemplate() {
        return new FigureTemplate(
                "wide-test",
                "宽图测试",
                "测试",
                null,
                List.of("测试"),
                "用于测试图库渲染后的 PNG 尺寸保留行为。",
                null,
                List.of(new FigureTemplate.Param("w", "number", null, null, null, "1", "宽度")),
                null,
                "\\begin{tikzpicture}\n\\draw (0,0)--(1,0);\n\\end{tikzpicture}",
                null   // elements
        );
    }

    private static final class StaticTikzCompiler extends TikzCompiler {
        private final Path path;

        private StaticTikzCompiler(Path path) {
            this.path = path;
        }

        @Override
        public Result compile(String code) {
            return new Result(path, null);
        }
    }

    private static final class RecordingTikzCompiler extends TikzCompiler {
        private String lastCode;

        @Override
        public Result compile(String code) {
            lastCode = code;
            return new Result(Path.of("dummy.png"), null);
        }
    }
}
