package com.yuanxuan.manim.config;

import com.yuanxuan.manim.service.ManimRenderService;
import com.yuanxuan.manim.service.YamlRenderService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

import java.net.http.HttpClient;

/**
 * 自动装配：宿主 Spring Boot 应用引入本模块依赖后，即可直接 @Autowired {@link ManimRenderService}。
 *
 * <p>仅依赖 JDK {@link HttpClient}，@Bean 方法签名不引用 Jackson / spring-web 类型，
 * 避免在 Spring Boot 4.x（Jackson 3，包名 tools.jackson）宿主中因类缺失而内省失败。
 * 通过 META-INF/spring/...AutoConfiguration.imports 注册，不会被宿主 @ComponentScan 重复扫描。
 */
@AutoConfiguration
@EnableConfigurationProperties(ManimProperties.class)
public class ManimAutoConfiguration {

    @Bean
    public HttpClient manimHttpClient(ManimProperties props) {
        return HttpClient.newBuilder()
                .connectTimeout(props.getConnectTimeout())
                .build();
    }

    @Bean
    public ManimRenderService manimRenderService(HttpClient manimHttpClient, ManimProperties props) {
        return new ManimRenderService(manimHttpClient, props);
    }

    @Bean
    public YamlRenderService yamlRenderService(ManimProperties props) {
        return new YamlRenderService(props);
    }
}
