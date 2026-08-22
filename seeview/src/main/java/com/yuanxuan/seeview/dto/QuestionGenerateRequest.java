package com.yuanxuan.seeview.dto;

import java.util.List;

/**
 * AI 生题（智能命题工作台）请求。
 *
 * <p>学科不单独设置，由大模型依据材料内容自动识别。
 *
 * @param types     题型清单（单选题/多选题/填空题/判断题/解答题的任意组合），必需
 * @param difficulty 难度：容易 | 中等 | 较难，缺省「中等」
 * @param count     总题量，1~30，缺省 5
 * @param prompt    用户补充命题要求，可选
 * @param fileName  上传材料文件名，可选
 * @param content   上传材料的文本内容，可选；文本类文件由前端读取后传入
 */
public record QuestionGenerateRequest(
        List<String> types,
        String difficulty,
        Integer count,
        String prompt,
        String fileName,
        String content
) {
}
