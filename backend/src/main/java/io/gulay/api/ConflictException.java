package io.gulay.api;


public class ConflictException extends RuntimeException {
    public ConflictException(String message) {
        super(message);
    }
}
