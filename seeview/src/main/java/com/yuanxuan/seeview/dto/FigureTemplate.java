package com.yuanxuan.seeview.dto;

import java.util.List;

/**
 * 图库模板（智能命题工作台配图用）。
 *
 * <p>一个模板 = 参数表 + TikZ 代码骨架。模板体开头用 {@code \def\参数名{值}} 声明区
 * 接收参数（这行由后端按参数值自动生成拼上去，模板文件里只留注释样例），
 * 正文坐标由 {@code \pgfmathsetmacro} 从参数算出，保证数量关系与题干一致。
 *
 * <p>存储：figure_library/figures/ 下每个模板一个 JSON 文件，与项目无数据库风格一致。
 */
public record FigureTemplate(
        String id,
        String name,
        String category,
        /** 上级通用模板 id（如 right-triangle 的 parent 是 general-triangle）；顶级通用模板为 null */
        String parent,
        List<String> tags,
        /** 一句话描述：什么题适合用这个模板（模型选图与检索的依据，必填且具体） */
        String desc,
        /** 反例描述：什么题不适合用（防止模型硬套），可选 */
        String whenNotToUse,
        /** 参数表：名称/类型/范围/默认值/中文说明 */
        List<Param> params,
        /** 参数约束表达式（如 "ab + bc < 20"），后端求值校验，违反拒绝渲染 */
        List<String> constraints,
        /** TikZ 代码骨架（\begin{tikzpicture}...\end{tikzpicture}） */
        String template
) {

    /**
     * 模板参数。
     *
     * @param name    参数名（TikZ \def 命令名，限小写字母与数字）
     * @param type    number | bool | string
     * @param min     number 型下界（含），可选
     * @param max     number 型上界（含），可选
     * @param options string 型取值白名单，可选
     * @param def     默认值（图库预览、模型缺参时使用），JSON 字段名为 default
     * @param desc    中文说明（图库试调面板与提示词注入用）
     */
    public record Param(String name, String type, Double min, Double max,
                        List<String> options,
                        @com.fasterxml.jackson.annotation.JsonProperty("default") String def,
                        String desc) {
    }

    /** 目录条目：图库列表与提示词注入用，不含 template 大字段 */
    public record Catalog(String id, String name, String category, String parent,
                          List<String> tags, String desc, String whenNotToUse,
                          List<Param> params) {
    }
}
