package com.seventeen17.commerceagent.approval;

import com.seventeen17.commerceagent.eligibility.AllowedAction;
import jakarta.persistence.LockModeType;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/**
 * Repository for authoritative approval records.
 *
 * <p>T052 uses the locked read for a decision so two approvers cannot both observe PENDING and then
 * overwrite each other. Binding is still re-checked again at the protected write boundary in T054.
 */
public interface ApprovalRequestRepository extends JpaRepository<ApprovalRequest, String> {

    List<ApprovalRequest> findAllByOrderByCreatedAtDesc();

    List<ApprovalRequest> findByStatusOrderByCreatedAtDesc(ApprovalStatus status);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select a from ApprovalRequest a where a.id = :id and a.userId = :userId")
    Optional<ApprovalRequest> findByIdAndUserIdForUpdate(
            @Param("id") String id, @Param("userId") String userId);


    Optional<ApprovalRequest> findByRunIdAndOrderIdAndActionAndStatus(
            String runId, String orderId, AllowedAction action, ApprovalStatus status);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select a from ApprovalRequest a where a.id = :id")
    Optional<ApprovalRequest> findByIdForUpdate(@Param("id") String id);
}
