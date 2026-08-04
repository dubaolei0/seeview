package com.yuanxuan.manim.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 发送给 Python 渲染微服务的请求体。
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class RenderRequest {

    /** scene.json 内容，作为 JSON 对象发送（Map / POJO / JsonNode） */
    private Object scene;

    /** 画质码：l/m/h/p/k */
    private String quality;
}
