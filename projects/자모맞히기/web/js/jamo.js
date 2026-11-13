export const UNITS = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎㅏㅐㅑㅒㅓㅔㅕㅖㅗㅛㅜㅠㅡㅣ';

export const SHIFTED = {
  'ㅂ': 'ㅃ',
  'ㅈ': 'ㅉ',
  'ㄷ': 'ㄸ',
  'ㄱ': 'ㄲ',
  'ㅅ': 'ㅆ',
  'ㅐ': 'ㅒ',
  'ㅔ': 'ㅖ'
};

export const KEY_ROWS = [
  ['ㅂ', 'ㅈ', 'ㄷ', 'ㄱ', 'ㅅ', 'ㅛ', 'ㅕ', 'ㅑ', 'ㅐ', 'ㅔ'],
  ['ㅁ', 'ㄴ', 'ㅇ', 'ㄹ', 'ㅎ', 'ㅗ', 'ㅓ', 'ㅏ', 'ㅣ'],
  ['ㅋ', 'ㅌ', 'ㅊ', 'ㅍ', 'ㅠ', 'ㅜ', 'ㅡ']
];

export const KEYMAP = {
  KeyQ: ['ㅂ', 'ㅃ'],
  KeyW: ['ㅈ', 'ㅉ'],
  KeyE: ['ㄷ', 'ㄸ'],
  KeyR: ['ㄱ', 'ㄲ'],
  KeyT: ['ㅅ', 'ㅆ'],
  KeyY: ['ㅛ', 'ㅛ'],
  KeyU: ['ㅕ', 'ㅕ'],
  KeyI: ['ㅑ', 'ㅑ'],
  KeyO: ['ㅐ', 'ㅒ'],
  KeyP: ['ㅔ', 'ㅖ'],
  KeyA: ['ㅁ', 'ㅁ'],
  KeyS: ['ㄴ', 'ㄴ'],
  KeyD: ['ㅇ', 'ㅇ'],
  KeyF: ['ㄹ', 'ㄹ'],
  KeyG: ['ㅎ', 'ㅎ'],
  KeyH: ['ㅗ', 'ㅗ'],
  KeyJ: ['ㅓ', 'ㅓ'],
  KeyK: ['ㅏ', 'ㅏ'],
  KeyL: ['ㅣ', 'ㅣ'],
  KeyZ: ['ㅋ', 'ㅋ'],
  KeyX: ['ㅌ', 'ㅌ'],
  KeyC: ['ㅊ', 'ㅊ'],
  KeyV: ['ㅍ', 'ㅍ'],
  KeyB: ['ㅠ', 'ㅠ'],
  KeyN: ['ㅜ', 'ㅜ'],
  KeyM: ['ㅡ', 'ㅡ']
};

const CHO = [...UNITS.slice(0, 19)];
const JUNG = [...'ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ'];

const JUNG_UNITS = [
  'ㅏ', 'ㅐ', 'ㅑ', 'ㅒ', 'ㅓ', 'ㅔ', 'ㅕ', 'ㅖ', 'ㅗ',
  'ㅗㅏ', 'ㅗㅐ', 'ㅗㅣ', 'ㅛ', 'ㅜ', 'ㅜㅓ', 'ㅜㅔ', 'ㅜㅣ',
  'ㅠ', 'ㅡ', 'ㅡㅣ', 'ㅣ'
];

const FINAL_UNITS = [
  '', 'ㄱ', 'ㄲ', 'ㄱㅅ', 'ㄴ', 'ㄴㅈ', 'ㄴㅎ', 'ㄷ', 'ㄹ', 'ㄹㄱ', 'ㄹㅁ',
  'ㄹㅂ', 'ㄹㅅ', 'ㄹㅌ', 'ㄹㅍ', 'ㄹㅎ', 'ㅁ', 'ㅂ', 'ㅂㅅ', 'ㅅ', 'ㅆ',
  'ㅇ', 'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'
];

const CHO_INDEX = new Map(CHO.map((unit, index) => [unit, index]));
const JUNG_INDEX = new Map(JUNG.map((unit, index) => [unit, index]));
const JONG_INDEX = new Map(FINAL_UNITS.map((unit, index) => [unit, index]));

const JUNG_COMPOUND = new Map([
  ['ㅗㅏ', 9],
  ['ㅗㅐ', 10],
  ['ㅗㅣ', 11],
  ['ㅜㅓ', 14],
  ['ㅜㅔ', 15],
  ['ㅜㅣ', 16],
  ['ㅡㅣ', 19]
]);

export function toUnits(word) {
  if (word.length === 0) return null;

  let units = '';
  for (const ch of word) {
    const code = ch.codePointAt(0) - 0xAC00;
    if (code < 0 || code > 11171) return null;

    const cho = Math.floor(code / 588);
    const jung = Math.floor((code % 588) / 28);
    const jong = code % 28;
    units += CHO[cho] + JUNG_UNITS[jung] + FINAL_UNITS[jong];
  }
  return units;
}

export function composeUnits(units) {
  let cho = -1;
  let jung = -1;
  let jong = 0;
  let out = '';

  const current = () => {
    if (cho >= 0 && jung >= 0) {
      return String.fromCharCode(0xAC00 + (cho * 21 + jung) * 28 + jong);
    }
    if (cho >= 0) return CHO[cho];
    if (jung >= 0) return JUNG[jung];
    return '';
  };

  const reset = (nextCho = -1, nextJung = -1, nextJong = 0) => {
    cho = nextCho;
    jung = nextJung;
    jong = nextJong;
  };

  for (const unit of units) {
    const nextCho = CHO_INDEX.get(unit);
    const nextJung = JUNG_INDEX.get(unit);

    if (nextCho !== undefined) {
      if (cho < 0) {
        if (jung >= 0) out += current();
        reset(nextCho);
      } else if (jung < 0) {
        out += current();
        reset(nextCho);
      } else if (jong === 0) {
        const finalIndex = JONG_INDEX.get(unit);
        if (finalIndex !== undefined) {
          jong = finalIndex;
        } else {
          out += current();
          reset(nextCho);
        }
      } else {
        const finalIndex = JONG_INDEX.get(FINAL_UNITS[jong] + unit);
        if (finalIndex !== undefined) {
          jong = finalIndex;
        } else {
          out += current();
          reset(nextCho);
        }
      }
      continue;
    }

    if (nextJung !== undefined) {
      if (cho < 0) {
        if (jung < 0) {
          jung = nextJung;
        } else {
          const combined = JUNG_COMPOUND.get(JUNG[jung] + unit);
          if (combined !== undefined) {
            jung = combined;
          } else {
            out += current();
            reset(-1, nextJung);
          }
        }
      } else if (jung < 0) {
        jung = nextJung;
      } else if (jong === 0) {
        const combined = JUNG_COMPOUND.get(JUNG[jung] + unit);
        if (combined !== undefined) {
          jung = combined;
        } else {
          out += current();
          reset(-1, nextJung);
        }
      } else {
        const finalUnits = FINAL_UNITS[jong];
        const lastUnit = finalUnits[finalUnits.length - 1];
        const left = finalUnits.slice(0, -1);
        const reducedJong = left === '' ? 0 : JONG_INDEX.get(left);
        out += String.fromCharCode(0xAC00 + (cho * 21 + jung) * 28 + reducedJong);
        reset(CHO_INDEX.get(lastUnit), nextJung);
      }
      continue;
    }

    out += current();
    out += unit;
    reset();
  }

  return out + current();
}
