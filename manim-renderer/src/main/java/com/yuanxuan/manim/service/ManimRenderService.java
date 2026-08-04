package com.yuanxuan.manim.service;


import com.alibaba.fastjson2.JSON;
import com.yuanxuan.manim.config.ManimProperties;
import com.yuanxuan.manim.dto.RenderRequest;
import com.yuanxuan.manim.dto.RenderResult;
import com.yuanxuan.manim.enums.Quality;
import com.yuanxuan.manim.exception.ManimRenderException;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

/**
 * 调用 Python manim 渲染微服务的可复用 Service。
 *
 * <p>HTTP 用 JDK {@link java.net.http.HttpClient}，JSON 用 fastjson2，
 * 不依赖 spring-web / Jackson，可在不同 Spring Boot 大版本的宿主中直接使用。
 *
 * 用法（宿主应用 @Autowired 后）：
 * <pre>
 * RenderResult r = manimRenderService.render(sceneJsonString, Quality.LOW);
 * if (r.successful()) {
 *     byte[] mp4 = manimRenderService.downloadVideo(r.getVideoUrl());
 * }
 * </pre>
 */
public class ManimRenderService {

    private final HttpClient httpClient;
    private final ManimProperties props;

    public ManimRenderService(HttpClient httpClient, ManimProperties props) {
        this.httpClient = httpClient;
        this.props = props;
    }

    /**
     * 渲染视频。
     *
     * @param scene   scene.json 内容（Map / POJO / fastjson2 的 JSONObject 等）
     * @param quality 画质
     * @return 渲染结果；渲染逻辑失败时 success=false 并携带 error，连接失败抛 {@link ManimRenderException}
     */
    public RenderResult render(Object scene, Quality quality) {
        String body;
        try {
            body = JSON.toJSONString(new RenderRequest(scene, quality.getCode()));
        } catch (Exception e) {
            throw new ManimRenderException("序列化请求失败: " + e.getMessage(), e);
        }
        return postRender(body);
    }

    /**
     * 渲染视频，scene 直接传 JSON 字符串（先解析为 JSON 对象再发送，避免双重编码）。
     */
    public RenderResult render(String sceneJson, Quality quality) {
        Object scene;
        try {
            scene = JSON.parse(sceneJson);
        } catch (Exception e) {
            throw new ManimRenderException("sceneJson 解析失败: " + e.getMessage(), e);
        }
        if (scene == null) {
            throw new ManimRenderException("sceneJson 解析为空");
        }
        return render(scene, quality);
    }

    /**
     * 下载已渲染的视频字节。
     *
     * @param videoUrl {@link RenderResult#getVideoUrl()} 返回的相对路径，如 /videos/xxx.mp4
     */
    public byte[] downloadVideo(String videoUrl) {
        try {
            URI uri = URI.create(props.getBaseUrl()).resolve(videoUrl);
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(uri)
                    .timeout(props.getTimeout())
                    .GET()
                    .build();
            HttpResponse<byte[]> resp = httpClient.send(request, HttpResponse.BodyHandlers.ofByteArray());
            if (resp.statusCode() >= 400) {
                throw new ManimRenderException("下载视频失败: HTTP " + resp.statusCode() + " - " + videoUrl);
            }
            return resp.body();
        } catch (ManimRenderException e) {
            throw e;
        } catch (Exception e) {
            throw new ManimRenderException("下载视频失败: " + videoUrl + " - " + e.getMessage(), e);
        }
    }

    private RenderResult postRender(String jsonBody) {
        try {
            URI uri = URI.create(props.getBaseUrl()).resolve("/render");
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(uri)
                    .header("Content-Type", "application/json")
                    .timeout(props.getTimeout())
                    .POST(HttpRequest.BodyPublishers.ofString(jsonBody, StandardCharsets.UTF_8))
                    .build();
            HttpResponse<String> resp = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            return parseResult(resp.body(), resp.statusCode());
        } catch (Exception e) {
            throw new ManimRenderException(
                    "调用 manim 服务失败 (" + props.getBaseUrl() + "): " + e.getMessage(), e);
        }
    }

    private RenderResult parseResult(String body, int status) {
        RenderResult rr;
        try {
            rr = (body == null || body.isBlank()) ? new RenderResult() : JSON.parseObject(body, RenderResult.class);
        } catch (Exception e) {
            rr = new RenderResult();
            rr.setError("解析响应失败: " + body);
        }
        if (status >= 400 && rr.getError() == null) {
            rr.setError("HTTP " + status);
        }
        return rr;
    }
}
