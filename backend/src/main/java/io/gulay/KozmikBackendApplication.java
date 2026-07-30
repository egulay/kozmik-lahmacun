package io.gulay;

import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@Slf4j
@SpringBootApplication
public class KozmikBackendApplication {

    public static void main(String[] args) {
        SpringApplication.run(KozmikBackendApplication.class, args);
        log.info("Kozmik Java backend started");
    }
}
