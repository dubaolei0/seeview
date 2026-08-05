package com.yuanxuan.seeview.controller;

import com.yuanxuan.seeview.dto.LectureBatchRequest;
import com.yuanxuan.seeview.dto.LectureRequest;
import com.yuanxuan.seeview.dto.LectureResult;
import com.yuanxuan.seeview.service.LectureGenerateService;
import dev.langchain4j.model.openai.OpenAiChatModel;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;

@RestController
@RequestMapping("/langchain")
public class LangChainController {

    @Autowired
    OpenAiChatModel chatModel;

    @Autowired
    private LectureGenerateService lectureGenerateService;

    @RequestMapping("/hello")
    public String hello() {
        return chatModel.chat("你好,今天周几");
    }

    /**
     * 讲题视频三段式生成：题目 -> 备课.md -> 讲稿.md -> yaml，并跑 Python 校验闭环。
     *
     * @param request 题目与参数（problem 必填）
     * @return 三份文档路径、正文与校验报告
     */
    @PostMapping("/lecture/generate")
    public LectureResult generate(@RequestBody LectureRequest request) throws IOException {
        if (request.problem() == null || request.problem().isBlank()) {
            throw new IllegalArgumentException("problem 不能为空");
        }
        return lectureGenerateService.generate(request);
    }

    /**
     * 多题批量生成（SSE）：上传一份含多道题的文档，后端按 {@code ---} 切分后并发生成，
     * 逐题推送 {@code start-item}/{@code item} 进度，最后 {@code done}。
     *
     * @param request 多题文档与参数（document 必填）
     * @return SSE 事件流
     */
    @PostMapping(value = "/lecture/generate-batch", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter generateBatch(@RequestBody LectureBatchRequest request) {
        if (request.document() == null || request.document().isBlank()) {
            throw new IllegalArgumentException("document 不能为空");
        }
        // 2h 超时：多题并发生成可能耗时较长
        SseEmitter emitter = new SseEmitter(7_200_000L);
        lectureGenerateService.generateBatch(request, emitter);
        return emitter;
    }
}
