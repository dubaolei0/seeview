package com.yuanxuan.seeview.common;

import java.io.Serializable;

/**
 * 统一返回结果类
 */
public class BaseResult<T> implements Serializable {

    private T data;
    private String message;
    private int code = CODE_SUCCESS;

    public BaseResult() {
    }

    public BaseResult(int code, String message, T data) {
        this.code = code;
        this.message = message;
        this.data = data;
    }

    public static <T> BaseResult<T> newSuccess() {
        return new BaseResult<>(CODE_SUCCESS, "success", null);
    }

    public static <T> BaseResult<T> newSuccess(T data) {
        return new BaseResult<>(CODE_SUCCESS, "", data);
    }

    public static <T> BaseResult<T> newSuccess(String message) {
        return new BaseResult<>(CODE_SUCCESS, message, null);
    }

    public static <T> BaseResult<T> newSuccess(T data, String message) {
        return new BaseResult<>(CODE_SUCCESS, message, data);
    }

    /**
     * 正常响应（链式），200
     */
    public BaseResult<T> ok(Object data, String msg) {
        this.code = CODE_SUCCESS;
        this.message = msg;
        this.data = (T) data;
        return this;
    }

    /**
     * 服务端错误，500
     */
    public static <T> BaseResult<T> newError(String message) {
        return new BaseResult<>(CODE_SERVER_ERROR, message, null);
    }

    public static <T> BaseResult<T> newError() {
        return new BaseResult<>(CODE_SERVER_ERROR, "未知", null);
    }

    /**
     * 能响应但业务异常，240
     */
    public static <T> BaseResult<T> newException(String message) {
        return new BaseResult<>(CODE_SUCCESS_ERR, message, null);
    }

    public BaseResult<T> error(int code, String msg, Object data) {
        this.code = code;
        this.message = msg;
        this.data = (T) data;
        return this;
    }

    public BaseResult<T> error(String msg, Object data) {
        this.message = msg;
        this.data = (T) data;
        return this;
    }

    public BaseResult<T> error(String msg) {
        this.code = CODE_SERVER_ERROR;
        this.message = msg;
        return this;
    }

    /**
     * 未认证，401
     */
    public static <T> BaseResult<T> newAuthError() {
        return new BaseResult<>(CODE_NO_LOGIN, "未认证", null);
    }

    /**
     * 请求禁止，403
     */
    public static BaseResult forbidden(String message) {
        return fail(CODE_FORBIDDEN, message);
    }

    /**
     * 未授权（业务权限不足），401 或 405 可按业务扩展
     */
    public static BaseResult unauthorized(String message) {
        return fail(CODE_NO_LOGIN, message);
    }

    public static BaseResult fail(int code, String message) {
        return new BaseResult<>(code, message, null);
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }

    public T getData() {
        return data;
    }

    public void setData(T data) {
        this.data = data;
    }

    public int getCode() {
        return code;
    }

    public void setCode(int code) {
        this.code = code;
    }

    /**
     * 正常响应，200
     */
    public static final Integer CODE_SUCCESS = 200;
    /**
     * 正常响应，提示，220
     */
    public static final Integer CODE_SUCCESS_TIP = 220;
    /**
     * 正常响应，警告，230
     */
    public static final Integer CODE_SUCCESS_WARN = 230;
    /**
     * 正常响应，但业务异常，240
     */
    public static final Integer CODE_SUCCESS_ERR = 240;
    /**
     * 未认证，401
     */
    public static final Integer CODE_NO_LOGIN = 401;
    /**
     * 请求禁止（XSS、CSRF等），403
     */
    public static final Integer CODE_FORBIDDEN = 403;
    /**
     * 业务授权禁止，405
     */
    public static final Integer CODE_NOT_ALLOWED = 405;
    /**
     * 系统未激活，420
     */
    public static final Integer CODE_NO_REG_SYS = 420;
    /**
     * 模块未激活，421
     */
    public static final Integer CODE_NO_REG_MODULE = 421;
    /**
     * 服务异常，500
     */
    public static final Integer CODE_SERVER_ERROR = 500;
}
