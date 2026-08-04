package com.yuanxuan.manim.enums;

/**
 * Manim 渲染画质，对应 manim CLI 的 -q 参数。
 */
public enum Quality {

    LOW("l", "480p15"),
    MEDIUM("m", "720p30"),
    HIGH("h", "1080p60"),
    PRODUCTION("p", "1440p60"),
    FOUR_K("k", "2160p60");

    private final String code;
    private final String label;

    Quality(String code, String label) {
        this.code = code;
        this.label = label;
    }

    public String getCode() {
        return code;
    }

    public String getLabel() {
        return label;
    }
}
