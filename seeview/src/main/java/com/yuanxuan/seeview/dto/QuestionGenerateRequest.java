package com.yuanxuan.seeview.dto;

import java.util.List;

/**
 * AI 生题（智能命题工作台）请求。
 *
 * <p>学科由用户在前端页面上直接选择（高中各学科），后端不再调大模型判定。
 *
 * @param types     题型清单（单选题/多选题/填空题/判断题/解答题的任意组合），必需
 * @param difficulty 难度：容易 | 中等 | 较难，缺省「中等」
 * @param count     总题量，1~30，缺省 5
 * @param subject   命题学科（前端选择，如 数学/物理/化学/语文 等）；空时提示词按「材料自识别」口径处理
 * @param prompt    用户补充命题要求，可选
 * @param fileName  上传材料文件名，可选
 * @param content   上传材料的文本内容，可选；文本类文件由前端读取后传入
 * @param figureTemplateId 指定配图模板 id，可选；指定后大模型只按该模板参数范围造题并填参数值
 *                         （id 固定、不再自行选图），后端按 fig 渲染出图。缺省走命题即选图 + 自由 TikZ 双轨。
 */
public record QuestionGenerateRequest(
        List<String> types,
        String difficulty,
        Integer count,
        String subject,
        String prompt,
        String fileName,
        String content,
        String figureTemplateId
) {
}
