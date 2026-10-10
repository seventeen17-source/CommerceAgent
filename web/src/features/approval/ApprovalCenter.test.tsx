import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import { ApprovalCenter, approvalError, type ApprovalRecord } from './ApprovalCenter'

const pending: ApprovalRecord = {
  approvalRequestId: 'approval-001',
  runId: 'run-001',
  orderId: 'us4-live-004',
  actionType: 'REFUND_ONLY',
  amount: 399,
  riskReason: 'APPROVAL_REQUIRED_BY_AMOUNT',
  status: 'PENDING',
  decidedBy: null,
  decidedAt: null,
  requestedAt: '2026-10-10T05:00:00Z',
  expiresAt: '2026-10-11T05:00:00Z',
}

function response(body: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('ApprovalCenter', () => {
  it('shows authoritative binding and never invents separate evidence', async () => {
    const fetch = vi.fn(async () => response([pending]))
    vi.stubGlobal('fetch', fetch)
    render(<ApprovalCenter />)
    fireEvent.change(screen.getByLabelText(/审批员 Token/), { target: { value: 'secret' } })
    fireEvent.click(screen.getByText('刷新待审批申请'))

    expect(await screen.findByText('APPROVAL_REQUIRED_BY_AMOUNT')).toBeTruthy()
    expect(screen.getAllByText('us4-live-004').length).toBeGreaterThan(0)
    expect(screen.getByText(/未提供独立证据明细/)).toBeTruthy()
    expect(fetch).toHaveBeenCalledWith(
      '/commerce/approvals?status=PENDING',
      expect.objectContaining({ headers: { Authorization: 'Bearer secret' } }),
    )
  })

  it('only changes displayed decision after Java confirms; confirmation is required', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(response([pending]))
      .mockResolvedValueOnce(response({ ...pending, status: 'APPROVED', decidedBy: 'approver-001' }))
    vi.stubGlobal('fetch', fetch)
    render(<ApprovalCenter />)
    fireEvent.change(screen.getByLabelText(/审批员 Token/), { target: { value: 'secret' } })
    fireEvent.click(screen.getByText('刷新待审批申请'))
    await screen.findByText('APPROVAL_REQUIRED_BY_AMOUNT')

    fireEvent.click(screen.getByText('Approve · 批准'))
    expect(fetch).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByText('确认 APPROVE'))

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    expect(fetch).toHaveBeenLastCalledWith(
      '/commerce/approvals/approval-001/decision',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ decision: 'APPROVE' }),
      }),
    )
    expect(await screen.findByText(/Java 已确认：APPROVED/)).toBeTruthy()
    expect(screen.queryByText('Approve · 批准')).toBeNull()
  })

  it('does not optimistically approve on conflict or repeat an unknown write', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(response([pending]))
      .mockResolvedValueOnce(response({}, 409))
    vi.stubGlobal('fetch', fetch)
    render(<ApprovalCenter />)
    fireEvent.change(screen.getByLabelText(/审批员 Token/), { target: { value: 'secret' } })
    fireEvent.click(screen.getByText('刷新待审批申请'))
    await screen.findByText('APPROVAL_REQUIRED_BY_AMOUNT')
    fireEvent.click(screen.getByText('Deny · 拒绝'))
    fireEvent.click(screen.getByText('确认 DENY'))

    expect(await screen.findByText(/请求冲突/)).toBeTruthy()
    expect(screen.getByText('Approve · 批准')).toBeTruthy()
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('maps authentication and permission errors to non-sensitive messages', () => {
    expect(approvalError(401)).toContain('过期')
    expect(approvalError(403)).toContain('APPROVER')
    expect(approvalError(409)).toContain('刷新')
  })
})
