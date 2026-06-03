import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import ShortAnalysisView from '../ShortAnalysisView.vue'

describe('ShortAnalysisView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders', () => {
    const wrapper = mount(ShortAnalysisView)
    expect(wrapper.find('h1').text()).toContain('Short')
  })
})
