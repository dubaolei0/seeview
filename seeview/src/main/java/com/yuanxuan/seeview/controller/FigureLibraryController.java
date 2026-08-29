package com.yuanxuan.seeview.controller;

import com.yuanxuan.seeview.dto.FigureTemplate;
import com.yuanxuan.seeview.service.FigureLibraryService;
import com.yuanxuan.seeview.service.FigureLibraryService.RenderResult;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/**
 * 图库接口（图库管理页 + 生题页配图参数面板共用）。
 *
 * <p>错误约定与 /question 系列一致：HTTP 200 + error 字段，前端按字段区分
 * （结构校验类的 IllegalArgumentException 除外，统一转 200 + error，前端不用分状态码处理）。
 */
@RestController
@RequestMapping("/figure")
public class FigureLibraryController {

    @Autowired
    private FigureLibraryService library;

    /** Map -> FigureTemplate（/preview 用），忽略未知字段 */
    private static final com.fasterxml.jackson.databind.ObjectMapper MAPPER =
            new com.fasterxml.jackson.databind.ObjectMapper()
                    .configure(com.fasterxml.jackson.databind.DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);

    /** 全部模板目录（图库页列表、生题提示词注入共用；不含 template 大字段） */
    @GetMapping("/list")
    public List<FigureTemplate.Catalog> list() {
        return library.list();
    }

    /** 按 id 取完整模板（编辑回显用） */
    @GetMapping("/get/{id}")
    public Map<String, Object> get(@PathVariable String id) {
        FigureTemplate t = library.get(id);
        return t == null ? Map.of("error", "图库中不存在模板: " + id) : Map.of("template", t);
    }

    /**
     * 保存模板（新建/更新）：结构校验 + 默认参数试编译，编译不过拒绝入库。
     *
     * @return 成功 {@code {"ok": true}}；失败 {@code {"error": 摘要}}
     */
    @PostMapping("/save")
    public Map<String, Object> save(@RequestBody FigureTemplate template) {
        try {
            library.save(template);
            return Map.of("ok", true);
        } catch (IllegalArgumentException e) {
            return Map.of("error", e.getMessage());
        }
    }

    /** 删除模板 */
    @DeleteMapping("/delete/{id}")
    public Map<String, Object> delete(@PathVariable String id) {
        try {
            return library.delete(id) ? Map.of("ok", true) : Map.of("error", "模板不存在: " + id);
        } catch (IllegalStateException e) {
            return Map.of("error", e.getMessage());
        }
    }

    /**
     * 渲染草稿模板（图库编辑器实时预览用）：不落盘，按编辑中的模板定义 + 参数渲染。
     *
     * @param body {@code {"template": 完整模板定义, "params": {参数名: 值}}}（params 可省，用默认值）
     * @return 成功 {@code {"path": PNG 绝对路径}}；失败 {@code {"error": 摘要}}
     */
    @PostMapping("/preview")
    public Map<String, String> preview(@RequestBody Map<String, Object> body) {
        if (body == null || body.get("template") == null) {
            return Map.of("error", "template 不能为空");
        }
        try {
            FigureTemplate t = MAPPER.convertValue(body.get("template"), FigureTemplate.class);
            @SuppressWarnings("unchecked")
            Map<String, Object> params = body.get("params") instanceof Map<?, ?> m
                    ? (Map<String, Object>) m : Map.of();
            RenderResult r = library.renderDraft(t, params);
            if (r.error() != null) {
                return Map.of("error", r.error());
            }
            return Map.of("path", r.path().toString().replace('\\', '/'));
        } catch (IllegalArgumentException e) {
            return Map.of("error", e.getMessage());
        }
    }

    /**
     * 渲染模板：参数校验 -> \def 注入 -> TikZ 编译。
     *
     * @param body {@code {"id": 模板id, "params": {参数名: 值}}}（params 可省，用默认值）
     * @return 成功 {@code {"path": PNG 绝对路径}}；失败 {@code {"error": 摘要}}
     */
    @PostMapping("/render")
    public Map<String, String> render(@RequestBody Map<String, Object> body) {
        if (body == null || body.get("id") == null || String.valueOf(body.get("id")).isBlank()) {
            return Map.of("error", "id 不能为空");
        }
        @SuppressWarnings("unchecked")
        Map<String, Object> params = body.get("params") instanceof Map<?, ?> m
                ? (Map<String, Object>) m : Map.of();
        RenderResult r = library.render(String.valueOf(body.get("id")).strip(), params);
        if (r.error() != null) {
            return Map.of("error", r.error());
        }
        return Map.of("path", r.path().toString().replace('\\', '/'));
    }
}
