package com.yuanxuan.seeview.controller;


import com.yuanxuan.manim.dto.RenderResult;
import com.yuanxuan.manim.enums.Quality;
import com.yuanxuan.manim.exception.ManimRenderException;
import com.yuanxuan.manim.service.ManimRenderService;
import com.yuanxuan.manim.service.YamlRenderService;
import lombok.extern.slf4j.Slf4j;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

/**
 * 智能体控制器
 * 提供网页搜索、文件问答和PPT生成的流式接口
 */
@RestController
@RequestMapping("/seeview")
@Slf4j
public class SeeViewController {

    @Autowired
    private ManimRenderService manimRenderService;

    @Autowired
    private YamlRenderService yamlRenderService;

    @PostMapping(value = "/get", produces = "text/event-stream;charset=UTF-8")
    public void getSeeView(@RequestParam("file") MultipartFile file) throws IOException {
        String json = new String(file.getBytes(), StandardCharsets.UTF_8);

        RenderResult r = manimRenderService.render(json, Quality.LOW);
        if (r.isSuccess()) {
            byte[] mp4 = manimRenderService.downloadVideo(r.getVideoUrl());
        }
    }

    /**
     * 上传 maths 讲题 yaml，本地子进程渲染成带配音 mp4 并返回下载。
     *
     * @param file    yaml 文件
     * @param quality 画质：low/medium/high（或 l/m/h），默认 medium
     * @param voice   可选 TTS 音色短名或 ID（如 longwan / liufei / zh_...）
     */
    @PostMapping(value = "/render", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<?> renderFromYaml(
            @RequestParam("file") MultipartFile file,
            @RequestParam(value = "quality", defaultValue = "medium") String quality,
            @RequestParam(value = "voice", required = false) String voice,
            @RequestParam(value = "saveTo", required = false) String saveTo) throws IOException {

        Quality q;
        try {
            q = parseQuality(quality);
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("{\"error\":\"" + escapeJson(e.getMessage()) + "\"}");
        }

        // saveTo 视为 yaml 完整路径：mp4 落盘到同目录、同名换 .mp4（与 yaml 并排）；为空则不落盘
        Path savePath = resolveSavePath(saveTo);

        byte[] mp4;
        try {
            mp4 = yamlRenderService.renderYaml(
                    new String(file.getBytes(), StandardCharsets.UTF_8), q, voice, savePath);
        } catch (ManimRenderException e) {
            log.error("render 失败: {}", e.getMessage(), e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("{\"error\":\"" + escapeJson(e.getMessage()) + "\"}");
        }

        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"lecture.mp4\"")
                .contentType(MediaType.parseMediaType("video/mp4"))
                .contentLength(mp4.length)
                .body(mp4);
    }

    /** saveTo 视为 yaml 路径，返回同目录同名 .mp4 路径；saveTo 为空或非法返回 null（不落盘）。 */
    private Path resolveSavePath(String saveTo) {
        if (saveTo == null || saveTo.isBlank()) {
            return null;
        }
        try {
            Path yamlPath = Path.of(saveTo).toAbsolutePath().normalize();
            String fileName = yamlPath.getFileName().toString();
            int dot = fileName.lastIndexOf('.');
            String stem = dot > 0 ? fileName.substring(0, dot) : fileName;
            return yamlPath.resolveSibling(stem + ".mp4");
        } catch (Exception e) {
            return null;
        }
    }

    private Quality parseQuality(String q) {
        return switch (q.toLowerCase()) {
            case "low", "l" -> Quality.LOW;
            case "high", "h" -> Quality.HIGH;
            default -> Quality.MEDIUM;
        };
    }

    private String escapeJson(String s) {
        return s == null ? "" : s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n");
    }
}
