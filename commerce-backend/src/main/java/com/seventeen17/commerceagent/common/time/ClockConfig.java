package com.seventeen17.commerceagent.common.time;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * T019：把"现在几点"提升为一个可替换的依赖。
 *
 * <p>为什么值得单独一个 Bean：物流停滞时长 = 现在 − 最后一次有效物流事件。如果业务代码直接写
 * {@code Instant.now()}，这个计算就**不可测**——今天写的 {@code assertEquals(120, stalledHours)} 明天就会因为
 * 时间流逝而失败，测试只能退化成"应该大于 48 吧"这种随时间漂移的模糊断言，而"阈值边界到底取不取等号"这种
 * 最容易出错的地方反而测不到。
 *
 * <p>注入 {@link Clock} 之后，测试用 {@code Clock.fixed(瞬时, UTC)} 把时间钉死，生产用系统时钟。这就是 Java 里
 * {@code Clock} 存在的意义：它不是为了"方便"，而是为了让**依赖时间的逻辑变成可精确断言的纯函数**。
 *
 * <p>统一使用 UTC：数据库列是 {@code TIMESTAMPTZ}，语义上存的是瞬时；用带时区的本地时钟去做差值，会引入与
 * 部署环境相关的偏差。
 */
@Configuration(proxyBeanMethods = false)
public class ClockConfig {

    @Bean
    Clock systemClock() {
        return Clock.systemUTC();
    }
}
