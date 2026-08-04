package cn.hollis.llm.mentor.manim.service;


import com.alibaba.fastjson2.JSONObject;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import com.yuanxuan.manim.config.ManimProperties;
import com.yuanxuan.manim.dto.RenderResult;
import com.yuanxuan.manim.enums.Quality;
import com.yuanxuan.manim.service.ManimRenderService;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

/**
 * 用 JDK 内置 {@link HttpServer} 起一个桩服务，验证 ManimRenderService 的请求构造与响应解析。
 * 不依赖 spring-web / MockRestServiceServer，与生产实现保持一致（JDK HttpClient + fastjson2）。
 */
class ManimRenderServiceTest {

    private HttpServer server;
    private ManimRenderService service;

    // /render 桩的可控响应
    private volatile int renderStatus = 200;
    private volatile String renderBody = "";
    private volatile String capturedRenderBody;

    // /videos/ 桩的可控响应
    private volatile byte[] videoBytes = new byte[0];

    @BeforeEach
    void setUp() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/render", this::handleRender);
        server.createContext("/videos/", this::handleVideo);

        ManimProperties props = new ManimProperties();
        props.setBaseUrl("http://127.0.0.1:" + server.getAddress().getPort());
        props.setTimeout(Duration.ofSeconds(10));
        props.setConnectTimeout(Duration.ofSeconds(5));

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(props.getConnectTimeout())
                .build();
        service = new ManimRenderService(client, props);

        server.start();
    }

    @AfterEach
    void tearDown() {
        if (server != null) {
            server.stop(0);
        }
    }

    @Test
    void render_success_shouldParseResult() {
        renderStatus = 200;
        renderBody = "{\"success\":true,\"videoUrl\":\"/videos/abc.mp4\","
                + "\"videoPath\":\"/tmp/abc.mp4\",\"durationMs\":1234}";

        Map<String, Object> scene = Map.of("background", "#1a1a2e", "steps", List.of());
        RenderResult rr = service.render(scene, Quality.LOW);

        assertTrue(rr.isSuccess());
        assertEquals("/videos/abc.mp4", rr.getVideoUrl());
        assertEquals(1234L, rr.getDurationMs());

        // 校验发出的请求体
        JSONObject sent = JSONObject.parseObject(capturedRenderBody);
        assertEquals("l", sent.getString("quality"));
        assertEquals("#1a1a2e", sent.getJSONObject("scene").getString("background"));
    }

    @Test
    void render_fromJsonString_shouldSendSceneAsObject() {
        renderStatus = 200;
        renderBody = "{\"success\":true,\"videoUrl\":\"/videos/x.mp4\",\"durationMs\":10}";

        String sceneJson = "{\"background\":\"#1a1a2e\",\"steps\":[]}";
        RenderResult rr = service.render(sceneJson, Quality.HIGH);

        assertTrue(rr.isSuccess());
        assertEquals("/videos/x.mp4", rr.getVideoUrl());

        JSONObject sent = JSONObject.parseObject(capturedRenderBody);
        assertEquals("h", sent.getString("quality"));
        assertEquals("#1a1a2e", sent.getJSONObject("scene").getString("background"));
    }

    @Test
    void render_failure_shouldReturnSuccessFalseWithError() {
        renderStatus = 500;
        renderBody = "{\"success\":false,\"error\":\"未生成视频文件\",\"stderr\":\"boom\"}";

        RenderResult rr = service.render(Map.of("steps", List.of()), Quality.LOW);

        assertFalse(rr.isSuccess());
        assertEquals("未生成视频文件", rr.getError());
        assertEquals("boom", rr.getStderr());
    }

    @Test
    void downloadVideo_shouldReturnBytes() {
        videoBytes = new byte[]{1, 2, 3};

        byte[] bytes = service.downloadVideo("/videos/abc.mp4");
        assertArrayEquals(new byte[]{1, 2, 3}, bytes);
    }

    private void handleRender(HttpExchange ex) throws IOException {
        capturedRenderBody = new String(ex.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
        byte[] resp = renderBody == null ? new byte[0] : renderBody.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().add("Content-Type", "application/json");
        ex.sendResponseHeaders(renderStatus, resp.length == 0 ? -1 : resp.length);
        try (OutputStream os = ex.getResponseBody()) {
            os.write(resp);
        }
    }

    private void handleVideo(HttpExchange ex) throws IOException {
        ex.getResponseHeaders().add("Content-Type", "video/mp4");
        ex.sendResponseHeaders(200, videoBytes.length == 0 ? -1 : videoBytes.length);
        try (OutputStream os = ex.getResponseBody()) {
            os.write(videoBytes);
        }
    }
}
