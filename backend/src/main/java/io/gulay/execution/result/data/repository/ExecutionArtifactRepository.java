package io.gulay.execution.result.data.repository;

import io.gulay.execution.result.data.model.ExecutionArtifactModel;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
public interface ExecutionArtifactRepository extends JpaRepository<ExecutionArtifactModel, UUID> {
    List<ExecutionArtifactModel> findByResultId(UUID resultId);

    @Modifying
    @Query(value = """
            update execution_artifact
            set deleted_at=now(), deletion_error_code=null
            where id=:artifactId and deleted_at is null
            """, nativeQuery = true)
    void markDeleted(UUID artifactId);

    @Modifying
    @Query(value = """
            update execution_artifact
            set deletion_error_code='OBJECT_DELETE_FAILED'
            where id=:artifactId and deleted_at is null
            """, nativeQuery = true)
    void markDeletionFailed(UUID artifactId);
}
