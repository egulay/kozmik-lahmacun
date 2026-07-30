FROM maven:3.9.9-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY pom.xml ./
COPY src ./src
RUN --mount=type=cache,target=/root/.m2 mvn -B -DskipTests package

FROM eclipse-temurin:17-jre-jammy
RUN groupadd --system kozmik \
    && useradd --system --gid kozmik --uid 10001 --create-home kozmik
WORKDIR /opt/kozmik
COPY --from=build /workspace/target/kozmik-backend-0.1.0-SNAPSHOT.jar app.jar
RUN mkdir -p /var/log/kozmik \
    && chown -R kozmik:kozmik /opt/kozmik /var/log/kozmik
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/opt/kozmik/app.jar"]
