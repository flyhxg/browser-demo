import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ThinkingBlock from '../ThinkingBlock.vue'
import type { ThinkingStep } from '../../types'

const STEPS: ThinkingStep[] = [
  { step: 1, description: 'analyzing' },
  { step: 2, description: 'planning' },
]

describe('ThinkingBlock', () => {
  it('renders the step count', () => {
    const wrapper = mount(ThinkingBlock, { props: { steps: STEPS, isComplete: false } })
    expect(wrapper.text()).toContain('2 steps')
  })

  it('expands by default while running (isComplete=false)', () => {
    const wrapper = mount(ThinkingBlock, { props: { steps: STEPS, isComplete: false } })
    expect(wrapper.find('.thinking-steps').exists()).toBe(true)
  })

  it('auto-collapses when isComplete flips to true and user has not toggled', async () => {
    const wrapper = mount(ThinkingBlock, { props: { steps: STEPS, isComplete: false } })
    expect(wrapper.find('.thinking-steps').exists()).toBe(true)
    await wrapper.setProps({ isComplete: true })
    expect(wrapper.find('.thinking-steps').exists()).toBe(false)
  })

  it('preserves user-expanded state when isComplete becomes true', async () => {
    const wrapper = mount(ThinkingBlock, { props: { steps: STEPS, isComplete: false } })
    // User clicks header to collapse: block should hide details
    await wrapper.find('.thinking-header').trigger('click')
    expect(wrapper.find('.thinking-steps').exists()).toBe(false)
    // User clicks again to re-expand
    await wrapper.find('.thinking-header').trigger('click')
    expect(wrapper.find('.thinking-steps').exists()).toBe(true)
    // Now completion arrives — user has expressed a preference, so block stays open
    await wrapper.setProps({ isComplete: true })
    expect(wrapper.find('.thinking-steps').exists()).toBe(true)
  })
})