import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TokenSelector from '../TokenSelector.vue'

describe('TokenSelector', () => {
  it('renders input', () => {
    const wrapper = mount(TokenSelector)
    expect(wrapper.find('input').exists()).toBe(true)
  })
})
