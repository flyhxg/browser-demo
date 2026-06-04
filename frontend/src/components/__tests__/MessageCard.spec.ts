import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MessageCard from '../MessageCard.vue'
import type { ExtendedChatMessage } from '../../types'

function makeMsg(overrides: Partial<ExtendedChatMessage> = {}): ExtendedChatMessage {
  return {
    role: 'assistant',
    text: 'Done.',
    timestamp: new Date('2026-06-04T10:00:00Z'),
    thinkingSteps: [{ step: 1, description: 'analyzing' }],
    toolCalls: [
      { name: 'get_price', arguments: { symbol: 'BTC' }, status: 'completed', source: { label: 'Binance Futures', url: 'https://www.binance.com/en/futures' } },
    ],
    ...overrides,
  }
}

describe('MessageCard', () => {
  it('renders thinking + tool + text in that order, even after text arrives', () => {
    const wrapper = mount(MessageCard, { props: { msg: makeMsg() } })
    const html = wrapper.html()
    const iThinking = html.indexOf('thinking-block')
    const iTool = html.indexOf('tool-call-block')
    const iText = html.indexOf('message-text')
    expect(iThinking).toBeGreaterThan(-1)
    expect(iTool).toBeGreaterThan(iThinking)
    expect(iText).toBeGreaterThan(iTool)
  })

  it('does not render thinking/tool blocks for user messages', () => {
    const wrapper = mount(MessageCard, {
      props: { msg: { role: 'user', text: 'hi', timestamp: new Date() } },
    })
    expect(wrapper.find('.thinking-block').exists()).toBe(false)
    expect(wrapper.find('.tool-call-block').exists()).toBe(false)
  })

  it('passes isComplete=true to ThinkingBlock when msg.text is set', () => {
    const wrapper = mount(MessageCard, { props: { msg: makeMsg({ text: 'hello' }) } })
    const tb = wrapper.findComponent({ name: 'ThinkingBlock' })
    expect(tb.exists()).toBe(true)
    expect(tb.props('isComplete')).toBe(true)
  })

  it('passes per-tool isComplete derived from tc.status', () => {
    const wrapper = mount(MessageCard, {
      props: {
        msg: makeMsg({
          toolCalls: [
            { name: 'a', arguments: {}, status: 'pending' },
            { name: 'b', arguments: {}, status: 'completed' },
          ],
        }),
      },
    })
    const blocks = wrapper.findAllComponents({ name: 'ToolCallBlock' })
    expect(blocks[0].props('isComplete')).toBe(false)
    expect(blocks[1].props('isComplete')).toBe(true)
  })
})