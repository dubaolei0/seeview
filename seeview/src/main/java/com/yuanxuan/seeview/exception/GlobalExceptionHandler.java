package com.yuanxuan.seeview.exception;


import com.yuanxuan.seeview.common.BaseResult;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.converter.HttpMessageNotWritableException;
import org.springframework.validation.BindException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingPathVariableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.async.AsyncRequestNotUsableException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;


import java.io.IOException;
import java.net.ConnectException;
import java.nio.channels.ClosedChannelException;
import java.util.Objects;
import java.util.stream.Collectors;


/**
 * 全局异常处理器
 */


@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);
    private static final String INTERNAL_SERVER_ERROR_MSG = "服务器内部错误，请联系管理员";

    private static final String CONNECT_ERROR_MSG = "服务调用失败，目标服务连接异常，请检查网络或目标服务状态";

    @ExceptionHandler(ConnectException.class)
    @ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
    public BaseResult handleConnectException(ConnectException e, HttpServletRequest request) {
        String msg = String.format("请求地址[%s]调用外部服务时发生连接异常：%s",
                request.getRequestURI(), CONNECT_ERROR_MSG);
        // 打印完整异常栈，便于排查具体连接失败的服务
        log.error(msg, e.getMessage());
        return BaseResult.fail(503, msg);
    }

    @ExceptionHandler(ClosedChannelException.class)
    @ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
    public BaseResult handleClosedChannelException(ClosedChannelException e, HttpServletRequest request) {
        String msg = String.format("请求地址[%s]调用外部服务时通道关闭：%s",
                request.getRequestURI(), CONNECT_ERROR_MSG);
        log.error(msg, e.getMessage());
        return BaseResult.fail(503, msg);
    }

    @ExceptionHandler(AsyncRequestNotUsableException.class)
    public void handleAsyncRequestNotUsableException(AsyncRequestNotUsableException e, HttpServletRequest request) {
        log.debug("SSE连接已断开: requestUri={}, cause={}",
                request.getRequestURI(), e.getCause() != null ? e.getCause().getMessage() : "未知原因");
    }

    @ExceptionHandler(IOException.class)
    public void handleIOException(IOException e, HttpServletRequest request) {
        String msg = e.getMessage();
        if (msg != null && (msg.contains("中止") || msg.contains("断开") || msg.contains("Broken pipe")
                || msg.contains("Connection reset") || msg.contains("已建立的连接"))) {
            log.debug("SSE客户端连接断开: requestUri={}, reason={}", request.getRequestURI(), msg);
        } else {
            log.error("请求地址[{}]发生IO异常", request.getRequestURI(), e);
        }
    }

    @ExceptionHandler(HttpMessageNotWritableException.class)
    public void handleHttpMessageNotWritableException(HttpMessageNotWritableException e, HttpServletRequest request) {
        log.debug("SSE响应已提交，无法写入错误响应: requestUri={}", request.getRequestURI());
    }

    @ExceptionHandler(HttpRequestMethodNotSupportedException.class)
    @ResponseStatus(HttpStatus.METHOD_NOT_ALLOWED)
    public BaseResult handleHttpRequestMethodNotSupported(HttpRequestMethodNotSupportedException e,
                                                          HttpServletRequest request) {
        String msg = String.format("请求地址[%s]不支持[%s]请求，支持的方法有：%s",
                request.getRequestURI(), e.getMethod(), Objects.requireNonNull(e.getSupportedMethods()));
        log.error(msg, e.getMessage());
        return BaseResult.fail(405, msg);
    }

    @ExceptionHandler(MissingPathVariableException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public BaseResult handleMissingPathVariableException(MissingPathVariableException e, HttpServletRequest request) {
        String msg = String.format("请求路径[%s]中缺少必需的路径变量[%s]",
                request.getRequestURI(), e.getVariableName());
        log.error(msg, e.getMessage());
        return BaseResult.fail(400, msg);
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public BaseResult handleMethodArgumentTypeMismatchException(MethodArgumentTypeMismatchException e,
                                                                HttpServletRequest request) {
        String requiredType = e.getRequiredType() != null ? e.getRequiredType().getSimpleName() : "未知类型";
        String msg = String.format("请求地址[%s]的参数[%s]类型不匹配，应为：%s，实际：%s",
                request.getRequestURI(), e.getName(), requiredType, e.getValue());
        log.error(msg, e.getMessage());
        return BaseResult.fail(400, msg);
    }

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public BaseResult handleIllegalArgumentException(IllegalArgumentException e, HttpServletRequest request) {
        log.warn("请求地址[{}]参数异常: {}", request.getRequestURI(), e.getMessage());
        return BaseResult.fail(400, e.getMessage());
    }

    @ExceptionHandler(IllegalStateException.class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    public BaseResult handleIllegalStateException(IllegalStateException e, HttpServletRequest request) {
        log.error("请求地址[{}]状态异常: {}", request.getRequestURI(), e.getMessage());
        return BaseResult.fail(500, e.getMessage());
    }

    @ExceptionHandler(BindException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public BaseResult handleBindException(BindException e) {
        String msg = e.getAllErrors().stream()
                .findFirst().map(err -> err.getDefaultMessage())
                .orElse("参数绑定验证失败");
        log.error("参数绑定异常：{}", msg, e.getMessage());
        return BaseResult.fail(400, msg);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public BaseResult handleMethodArgumentNotValidException(MethodArgumentNotValidException e) {
        String msg = e.getBindingResult().getFieldErrors().stream()
                .map(err -> err.getField() + ": " + err.getDefaultMessage())
                .collect(Collectors.joining("; "));
        log.error("参数验证异常：{}", msg, e.getMessage());
        return BaseResult.fail(400, "参数验证失败: " + msg);
    }

    @ExceptionHandler(ConstraintViolationException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public BaseResult handleConstraintViolationException(ConstraintViolationException e) {
        String msg = e.getConstraintViolations().stream()
                .map(ConstraintViolation::getMessage)
                .collect(Collectors.joining("; "));
        log.error("参数约束异常：{}", msg, e.getMessage());
        return BaseResult.fail(400, "参数验证失败: " + msg);
    }

    @ExceptionHandler(RuntimeException.class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    public BaseResult handleRuntimeException(RuntimeException e, HttpServletRequest request) {
        log.error("请求地址[{}]发生运行时异常", request.getRequestURI(), e);
        return BaseResult.fail(500, INTERNAL_SERVER_ERROR_MSG);
    }

    @ExceptionHandler(Exception.class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    public BaseResult handleException(Exception e, HttpServletRequest request) {
        log.error("请求地址[{}]处理失败", request.getRequestURI(), e);
        return BaseResult.fail(500, INTERNAL_SERVER_ERROR_MSG);
    }
}
