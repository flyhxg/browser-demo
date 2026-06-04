import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ToolCallBlock from '../ToolCallBlock.vue'
import type { ToolCall } from '../../types'

const baseTc: ToolCall = {
  name: 'get_price',
  arguments: { symbol: 'BTC' },
  status: 'completed',
  result: { price_usd: 65000 },
  source: { label: 'Binance Futures', url: 'https://www.binance.com/en/futures' },
}

describe('ToolCallBlock', () => {
  it('renders the data-source chip when source is set', () => {
    const wrapper = mount(ToolCallBlock, { props: { toolCall: baseTc, isComplete: true } })
    const chip = wrapper.find('.tool-source')
    expect(chip.exists()).toBe(true)
    expect(chip.text()).toBe('Binance Futures ↗')
  })

  it('renders chip as <a> when source.url is non-empty', () => {
    const wrapper = mount(ToolCallBlock, { props: { toolCall: baseTc, isComplete: true } })
    const anchor = wrapper.find('a.tool-source')
    expect(anchor.exists()).toBe(true)
    expect(anchor.attributes('href')).toBe('https://www.binance.com/en/futures')
  })

  it('renders chip as <span> when source.url is empty', () => {
    const wrapper = mount(ToolCallBlock, {
      props: { toolCall: { ...baseTc, source: { label: 'LLM', url: '' } }, isComplete: true },
    })
    expect(wrapper.find('a.tool-source').exists()).toBe(false)
    expect(wrapper.find('span.tool-source').exists()).toBe(true)
  })

  it('expands by default while running (isComplete=false)', () => {
    const wrapper = mount(ToolCallBlock, {
      props: { toolCall: { ...baseTc, status: 'pending' }, isComplete: false },
    })
    expect(wrapper.find('.tool-arguments').exists()).toBe(true)
  })

  it('auto-collapses on isComplete=true when user has not toggled', async () => {
    const wrapper = mount(ToolCallBlock, { props: { toolCall: baseTc, isComplete: false } })
    expect(wrapper.find('.tool-arguments').exists()).toBe(true)
    await wrapper.setProps({ isComplete: true })
    expect(wrapper.find('.tool-arguments').exists()).toBe(false)
  })

  it('preserves user-expanded state when isComplete becomes true', async () => {
    const wrapper = mount(ToolCallBlock, { props: { toolCall: baseTc, isComplete: false } })
    await wrapper.find('.tool-call-header').trigger('click') // collapse
    expect(wrapper.find('.tool-arguments').exists()).toBe(false)
    await wrapper.find('.tool-call-header').trigger('click') // expand
    expect(wrapper.find('.tool-arguments').exists()).toBe(true)
    await wrapper.setProps({ isComplete: true })
    expect(wrapper.find('.tool-arguments').exists()).toBe(true)
  })
})