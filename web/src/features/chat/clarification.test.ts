import { describe, expect, it } from 'vitest'

import { clarificationTextFor, headlineFor } from './clarification'

describe('clarificationTextFor', () => {
  it('asks a different question for each kind', () => {
    const questions = [
      clarificationTextFor('ORDER_AMBIGUOUS'),
      clarificationTextFor('ORDER_NO_MATCH'),
      clarificationTextFor('INTENT_UNKNOWN'),
    ]

    expect(new Set(questions).size).toBe(3)
  })

  it('never tells a customer that several orders match when none of them did', () => {
    // The regression this file was created for: `ORDER_NO_MATCH` used to fall through to the
    // "I did not understand you" sentence, so a customer whose product simply had no matching order
    // was told their *request* was unclear -- a different problem, and not theirs to fix.
    const noMatch = clarificationTextFor('ORDER_NO_MATCH')

    expect(noMatch).toContain('没找到')
    expect(noMatch).not.toContain('诉求')
    expect(noMatch).not.toBe(clarificationTextFor('ORDER_AMBIGUOUS'))
  })
})

describe('headlineFor', () => {
  it('does not ask a waiting customer for information while an approver decides', () => {
    expect(headlineFor('WAITING_APPROVAL')).not.toBe(headlineFor('WAITING_USER'))
    expect(headlineFor('WAITING_APPROVAL')).toContain('人工审核')
  })

  it('answers in words for every status, never with the enum', () => {
    for (const status of ['COMPLETED', 'FAILED', 'SAFE_STOP', 'ESCALATED', 'RUNNING']) {
      expect(headlineFor(status)).not.toContain('_')
    }
  })
})
