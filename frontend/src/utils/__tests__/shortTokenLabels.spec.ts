import { describe, it, expect } from 'vitest'
import {
  longCrowdClass,
  longCrowdHintText,
  extensionClass,
  extensionHintText,
} from '../shortTokenLabels'

describe('shortTokenLabels', () => {
  describe('longCrowdClass', () => {
    it('returns "extreme" when long_crowdedness > 0.7', () => {
      expect(longCrowdClass(0.8)).toBe('extreme')
      expect(longCrowdClass(1.0)).toBe('extreme')
    })

    it('returns "high" when 0.5 < long_crowdedness <= 0.7', () => {
      expect(longCrowdClass(0.6)).toBe('high')
    })

    it('returns "medium" when 0.3 < long_crowdedness <= 0.5', () => {
      expect(longCrowdClass(0.4)).toBe('medium')
    })

    it('returns "low" when long_crowdedness <= 0.3', () => {
      expect(longCrowdClass(0.3)).toBe('low')
      expect(longCrowdClass(0.0)).toBe('low')
    })

    it('falls back to "low" for missing/undefined input', () => {
      expect(longCrowdClass(undefined)).toBe('low')
    })
  })

  describe('longCrowdHintText', () => {
    it('returns the extreme-crowded hint when score > 0.7', () => {
      expect(longCrowdHintText(0.8)).toMatch(/极度拥挤/)
    })

    it('returns the elevated hint when 0.5 < score <= 0.7', () => {
      expect(longCrowdHintText(0.6)).toMatch(/偏高/)
    })

    it('returns the balanced hint when 0.3 < score <= 0.5', () => {
      expect(longCrowdHintText(0.4)).toMatch(/平衡/)
    })

    it('returns the light-position hint when score <= 0.3', () => {
      expect(longCrowdHintText(0.0)).toMatch(/较轻/)
      expect(longCrowdHintText(0.3)).toMatch(/较轻/)
    })

    it('falls back to the light-position hint for missing/undefined input', () => {
      expect(longCrowdHintText(undefined)).toMatch(/较轻/)
    })
  })

  describe('class and hint thresholds agree for long_crowdedness', () => {
    // Pairs of (class, hint) at representative boundary+1 values.
    // A divergence between class and hint thresholds caused a real bug
    // (score 0.45 got class 'medium' but hint '偏高' intended for >0.5).
    // The pairs below pin the class/hint bands together: any future
    // realignment of one without the other will be caught immediately.
    const expected = [
      { v: 0.71, klass: 'extreme', hint: /极度拥挤/ },
      { v: 0.51, klass: 'high', hint: /偏高/ },
      { v: 0.31, klass: 'medium', hint: /平衡/ },
      { v: 0.21, klass: 'low', hint: /较轻/ },
      { v: 0.0, klass: 'low', hint: /较轻/ },
    ]
    for (const { v, klass, hint } of expected) {
      it(`at v=${v} class is "${klass}" and hint matches ${hint}`, () => {
        expect(longCrowdClass(v)).toBe(klass)
        expect(longCrowdHintText(v)).toMatch(hint)
      })
    }

    it('class and hint band boundaries (0.7/0.5/0.3) agree', () => {
      // Just above each boundary -> non-default band.
      expect(longCrowdClass(0.71)).toBe('extreme')
      expect(longCrowdHintText(0.71)).toMatch(/极度拥挤/)
      expect(longCrowdClass(0.51)).toBe('high')
      expect(longCrowdHintText(0.51)).toMatch(/偏高/)
      expect(longCrowdClass(0.31)).toBe('medium')
      expect(longCrowdHintText(0.31)).toMatch(/平衡/)
      // At/below each boundary -> falls into the lower band.
      expect(longCrowdClass(0.7)).toBe('high')
      expect(longCrowdHintText(0.7)).toMatch(/偏高/)
      expect(longCrowdClass(0.5)).toBe('medium')
      expect(longCrowdHintText(0.5)).toMatch(/平衡/)
      expect(longCrowdClass(0.3)).toBe('low')
      expect(longCrowdHintText(0.3)).toMatch(/较轻/)
    })
  })

  describe('extensionClass', () => {
    it('returns "extreme" when extension_score > 0.7', () => {
      expect(extensionClass(0.8)).toBe('extreme')
      expect(extensionClass(1.0)).toBe('extreme')
    })

    it('returns "high" when 0.4 < extension_score <= 0.7', () => {
      expect(extensionClass(0.5)).toBe('high')
    })

    it('returns "medium" when 0.2 < extension_score <= 0.4', () => {
      expect(extensionClass(0.3)).toBe('medium')
    })

    it('returns "low" when extension_score <= 0.2', () => {
      expect(extensionClass(0.2)).toBe('low')
      expect(extensionClass(0.0)).toBe('low')
    })

    it('falls back to "low" for missing/undefined input', () => {
      expect(extensionClass(undefined)).toBe('low')
    })
  })

  describe('extensionHintText', () => {
    it('returns the top-near hint when score > 0.7', () => {
      expect(extensionHintText(0.8)).toMatch(/顶部/)
    })

    it('returns the clear-uptrend hint when 0.4 < score <= 0.7', () => {
      expect(extensionHintText(0.5)).toMatch(/涨势/)
    })

    it('returns the some-up-move hint when 0.2 < score <= 0.4', () => {
      expect(extensionHintText(0.3)).toMatch(/涨幅/)
    })

    it('returns the not-extended hint when score <= 0.2', () => {
      expect(extensionHintText(0.0)).toMatch(/未到位|风险大/)
      expect(extensionHintText(0.2)).toMatch(/未到位|风险大/)
    })

    it('falls back to the not-extended hint for missing/undefined input', () => {
      expect(extensionHintText(undefined)).toMatch(/未到位|风险大/)
    })
  })
})
