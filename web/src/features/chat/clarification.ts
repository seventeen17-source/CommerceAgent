/**
 * The words a customer reads, kept out of the component.
 *
 * Why these live here: both functions are pure mappings (a status or a kind -> one sentence), and a
 * component file cannot be tested without dragging a browser, a fetch mock and React into the test.
 * They are also the part of the console that has actually been wrong: `ORDER_NO_MATCH` once fell
 * through to the "I did not understand you" wording, which describes a different problem.
 */

/** The three ways a run can stop to ask something. Not interchangeable -- see `clarificationTextFor`. */
export type ClarificationKind = 'INTENT_UNKNOWN' | 'ORDER_AMBIGUOUS' | 'ORDER_NO_MATCH'

/** Status is a state, not a label: map it to words a customer would use, never print the enum. */
export function headlineFor(status: string): string {
  if (status === 'WAITING_USER') {
    return '需要你补充一点信息'
  }
  if (status === 'WAITING_APPROVAL') {
    // Waiting on an approver is not something the customer can act on, so it must not read like a
    // request for more information -- that would send them looking for something to supply.
    return '已提交人工审核，请等待结果'
  }
  if (status === 'RUNNING') {
    // The create call drives the graph, so this should not happen; saying so honestly beats a
    // spinner that never resolves.
    return '还在处理中，请稍后刷新页面查看结果'
  }
  if (status === 'SAFE_STOP' || status === 'ESCALATED') {
    return '已转人工处理'
  }
  if (status === 'FAILED') {
    return '处理失败'
  }
  return '处理完成'
}

/**
 * One question per kind, in the customer's words.
 *
 * `ORDER_NO_MATCH` says the *clue* found nothing -- it is not "several match" and not "I did not
 * understand you", and saying either would be a lie about what the system actually knows.
 */
export function clarificationTextFor(kind: ClarificationKind): string {
  if (kind === 'ORDER_AMBIGUOUS') {
    return '你名下有好几笔订单，请告诉我是哪一笔。'
  }
  if (kind === 'ORDER_NO_MATCH') {
    return '我没找到你说的那件商品的订单，请确认是下面哪一笔（只列最近几笔）。'
  }
  return '我还不太确定你的诉求，能再说明一下吗？'
}
