package io.gulay.chat.client;

import java.util.function.Consumer;

public interface PythonChatClient {
    void stream(PythonChatContracts.StreamRequest request,
                Consumer<PythonChatContracts.StreamEvent> eventConsumer);

    PythonChatContracts.ClassificationResponse classify(
            PythonChatContracts.ClassificationRequest request);
}
