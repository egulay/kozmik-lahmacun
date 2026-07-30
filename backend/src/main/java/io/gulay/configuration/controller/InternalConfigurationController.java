package io.gulay.configuration.controller;

import io.gulay.configuration.data.service.EffectiveConfigurationService;
import io.gulay.configuration.dto.EffectiveConfigurationDtos;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal/v1/config")
@RequiredArgsConstructor
public class InternalConfigurationController {
    private final EffectiveConfigurationService service;

    @GetMapping("/effective")
    EffectiveConfigurationDtos.EffectiveConfiguration effective() {
        return service.effective();
    }
}
