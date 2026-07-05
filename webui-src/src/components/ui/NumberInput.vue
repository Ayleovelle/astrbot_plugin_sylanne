<script setup lang="ts">
// Numeric input primitive — same chrome as TextInput, mono digits, emits a
// real number (not a string) on v-model:number.
withDefaults(
  defineProps<{
    modelValue: number
    min?: number
    max?: number
    step?: number
    disabled?: boolean
  }>(),
  {
    step: 1,
    disabled: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: number]
}>()

function onInput(e: Event): void {
  const raw = (e.target as HTMLInputElement).value
  const n = Number(raw)
  if (raw !== '' && !Number.isNaN(n)) {
    emit('update:modelValue', n)
  }
}
</script>

<template>
  <input
    class="number-input mono"
    type="number"
    :value="modelValue"
    :min="min"
    :max="max"
    :step="step"
    :disabled="disabled"
    @input="onInput"
  />
</template>

<style scoped>
.number-input {
  width: 100%;
  padding: var(--space-4) var(--space-5);
  font-size: var(--font-sm);
  color: var(--text);
  background: var(--input-bg);
  border: 1px solid var(--card-border);
  border-radius: var(--r-sm);
  outline: none;
  transition: border-color var(--dur-mid) ease, box-shadow var(--dur-mid) ease;
}
.number-input:disabled {
  cursor: default;
  opacity: 0.5;
}
.number-input:focus {
  border-color: var(--accent);
  box-shadow: var(--ring-focus);
}

/* browser spinner chrome is dropped — value still steppable via keyboard
   up/down arrows, min/max/step remain enforced by the native input */
.number-input::-webkit-outer-spin-button,
.number-input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
.number-input {
  -moz-appearance: textfield;
}
</style>
