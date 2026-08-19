package com.yuanxuan.manim.service;

import com.yuanxuan.manim.config.ManimProperties;
import com.yuanxuan.manim.enums.Quality;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

/**
 * {@link YamlRenderService} 的纯逻辑单测（不真起 python 子进程）。
 *
 * <p>覆盖计划中要求的三个验证点：
 * <ol>
 *   <li>quality 映射：LOW/MEDIUM/HIGH -> low/medium/high；PRODUCTION/FOUR_K 抛 IllegalArgumentException</li>
 *   <li>命令构造：python -m renderer.render <yaml> --quality <q> [--tts-voice <v>]</li>
 *   <li>环境变量注入：PYTHONIOENCODING=utf-8；DASHSCOPE_API_KEY 仅在配置了 key 时注入</li>
 * </ol>
 *
 * <p>包级私有方法（buildCommand / mapQuality / applyEnvironment）可直接访问。
 * 真正跑 python 的集成测试需 venv + manim + xelatex + ffmpeg 环境，属可选，此处不涉及。
 */
class YamlRenderServiceTest {

    private static final String PYTHON = "/path/to/python.exe";
    private static final String YAML = "/tmp/see_test.yaml";

    private YamlRenderService newService(String dashscopeKey) {
        ManimProperties props = new ManimProperties();
        props.setPython(PYTHON);
        props.setEngineDir("/tmp/lecture_pipeline");
        props.setDashscopeKey(dashscopeKey);
        props.setTimeout(Duration.ofSeconds(60));
        props.setConnectTimeout(Duration.ofSeconds(5));
        return new YamlRenderService(props);
    }

    // ---------------- mapQuality ----------------

    @Test
    void mapQuality_lowMediumHigh() {
        YamlRenderService svc = newService(null);
        assertEquals("low", svc.mapQuality(Quality.LOW));
        assertEquals("medium", svc.mapQuality(Quality.MEDIUM));
        assertEquals("high", svc.mapQuality(Quality.HIGH));
    }

    @Test
    void mapQuality_productionAndFourKNotSupported() {
        YamlRenderService svc = newService(null);
        assertThrows(IllegalArgumentException.class, () -> svc.mapQuality(Quality.PRODUCTION));
        assertThrows(IllegalArgumentException.class, () -> svc.mapQuality(Quality.FOUR_K));
    }

    // ---------------- buildCommand ----------------

    @Test
    void buildCommand_withoutVoice() {
        YamlRenderService svc = newService(null);
        List<String> cmd = svc.buildCommand(PYTHON, YAML, Quality.MEDIUM, null);

        assertEquals(List.of(
                PYTHON, "-m", "renderer.render", YAML, "--quality", "medium"
        ), cmd);
        assertFalse(cmd.contains("--tts-voice"), "无 voice 时不应带 --tts-voice");
    }

    @Test
    void buildCommand_withVoice() {
        YamlRenderService svc = newService(null);
        List<String> cmd = svc.buildCommand(PYTHON, YAML, Quality.LOW, "longwan");

        assertEquals(PYTHON, cmd.get(0));
        assertEquals("-m", cmd.get(1));
        assertEquals("renderer.render", cmd.get(2));
        assertEquals(YAML, cmd.get(3));
        assertEquals("--quality", cmd.get(4));
        assertEquals("low", cmd.get(5));
        // voice 跟在 --tts-voice 之后
        int idx = cmd.indexOf("--tts-voice");
        assertNotEquals(-1, idx, "应包含 --tts-voice");
        assertEquals("longwan", cmd.get(idx + 1));
    }

    @Test
    void buildCommand_blankVoiceIsIgnored() {
        YamlRenderService svc = newService(null);
        // 空串与纯空白都不应注入 --tts-voice
        for (String blank : new String[]{"", "   ", "\t"}) {
            List<String> cmd = svc.buildCommand(PYTHON, YAML, Quality.HIGH, blank);
            assertFalse(cmd.contains("--tts-voice"),
                    "空白 voice 不应带 --tts-voice: [" + blank + "]");
            assertEquals(6, cmd.size(), "无 voice 时命令应为 6 段");
        }
    }

    @Test
    void buildCommand_doubaoVoiceIdPassedAsIs() {
        YamlRenderService svc = newService(null);
        // zh_ 开头的豆包音色 ID 应原样透传，由 python 侧 auto 推断 provider
        String voice = "zh_male_liufei_uranus_bigtts";
        List<String> cmd = svc.buildCommand(PYTHON, YAML, Quality.HIGH, voice);
        int idx = cmd.indexOf("--tts-voice");
        assertEquals(voice, cmd.get(idx + 1));
    }

    @Test
    void buildCommand_qualityMappedInCommand() {
        YamlRenderService svc = newService(null);
        // 命令里的 --quality 值必须与 mapQuality 一致（low/medium/high，非 l/m/h）
        assertEquals("low", qualityInCommand(svc, Quality.LOW));
        assertEquals("medium", qualityInCommand(svc, Quality.MEDIUM));
        assertEquals("high", qualityInCommand(svc, Quality.HIGH));
    }

    // ---------------- buildCommand: speech rate ----------------

    @Test
    void buildCommand_withSpeechRate() {
        YamlRenderService svc = newService(null);
        List<String> cmd = svc.buildCommand(PYTHON, YAML, Quality.MEDIUM, null, null, 1.25);

        int idx = cmd.indexOf("--speech-rate");
        assertNotEquals(-1, idx, "应包含 --speech-rate");
        assertEquals("1.25", cmd.get(idx + 1));
    }

    @Test
    void buildCommand_defaultOrBlankSpeechRateOmitted() {
        YamlRenderService svc = newService(null);
        // 1.0 = 默认语速，不应传 --speech-rate（保持与历史命令一致）
        assertFalse(svc.buildCommand(PYTHON, YAML, Quality.MEDIUM, null, null, 1.0)
                .contains("--speech-rate"));
        assertFalse(svc.buildCommand(PYTHON, YAML, Quality.MEDIUM, null, null, null)
                .contains("--speech-rate"));
    }

    private String qualityInCommand(YamlRenderService svc, Quality q) {
        List<String> cmd = svc.buildCommand(PYTHON, YAML, q, null);
        int idx = cmd.indexOf("--quality");
        return cmd.get(idx + 1);
    }

    // ---------------- applyEnvironment ----------------

    @Test
    void applyEnvironment_setsPythonioencodingAlways() {
        YamlRenderService svc = newService(null);
        ProcessBuilder pb = new ProcessBuilder("echo", "hi");
        pb.environment().clear();   // 排除继承的宿主环境变量，保证断言确定

        svc.applyEnvironment(pb);

        Map<String, String> env = pb.environment();
        assertEquals("utf-8", env.get("PYTHONIOENCODING"));
        assertFalse(env.containsKey("DASHSCOPE_API_KEY"),
                "未配 key 时不应注入 DASHSCOPE_API_KEY");
    }

    @Test
    void applyEnvironment_injectsDashscopeKeyWhenConfigured() {
        YamlRenderService svc = newService("dashscope-test-key-123");
        ProcessBuilder pb = new ProcessBuilder("echo", "hi");
        pb.environment().clear();

        svc.applyEnvironment(pb);

        Map<String, String> env = pb.environment();
        assertEquals("utf-8", env.get("PYTHONIOENCODING"));
        assertEquals("dashscope-test-key-123", env.get("DASHSCOPE_API_KEY"));
    }

    @Test
    void applyEnvironment_blankKeyNotInjected() {
        YamlRenderService svc = newService("   ");
        ProcessBuilder pb = new ProcessBuilder("echo", "hi");
        pb.environment().clear();

        svc.applyEnvironment(pb);

        Map<String, String> env = pb.environment();
        assertEquals("utf-8", env.get("PYTHONIOENCODING"));
        assertFalse(env.containsKey("DASHSCOPE_API_KEY"),
                "纯空白 key 视同未配，不应注入 DASHSCOPE_API_KEY");
    }

    @Test
    void applyEnvironment_injectsDoubaoCredsWhenConfigured() {
        ManimProperties props = new ManimProperties();
        props.setPython(PYTHON);
        props.setEngineDir("/tmp/lecture_pipeline");
        props.setDoubaoAppid("doubao-appid-1");
        props.setDoubaoToken("doubao-token-2");
        props.setDoubaoCluster("seed-tts-2.0");
        YamlRenderService svc = new YamlRenderService(props);
        ProcessBuilder pb = new ProcessBuilder("echo", "hi");
        pb.environment().clear();

        svc.applyEnvironment(pb);

        Map<String, String> env = pb.environment();
        assertEquals("doubao-appid-1", env.get("DOUBAO_APPID"));
        assertEquals("doubao-token-2", env.get("DOUBAO_TOKEN"));
        assertEquals("seed-tts-2.0", env.get("DOUBAO_CLUSTER"));
    }

    @Test
    void applyEnvironment_doubaoBlankNotInjected() {
        YamlRenderService svc = newService(null);
        ProcessBuilder pb = new ProcessBuilder("echo", "hi");
        pb.environment().clear();

        svc.applyEnvironment(pb);

        Map<String, String> env = pb.environment();
        assertFalse(env.containsKey("DOUBAO_APPID"), "未配豆包凭据时不应注入 DOUBAO_APPID");
        assertFalse(env.containsKey("DOUBAO_TOKEN"), "未配豆包凭据时不应注入 DOUBAO_TOKEN");
    }
}
