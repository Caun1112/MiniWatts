const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const store = new Map();
const context = vm.createContext({localStorage: {
  getItem: key => store.get(key) ?? null,
  setItem: (key, value) => store.set(key, value)
}, navigator: {language: 'en-US'}});
const source = fs.readFileSync('Vendor/ChargeLimiter/www/js/utils.js', 'utf8');
vm.runInContext(source.slice(0, source.indexOf('function range(')), context);
assert.equal(context.get_local_lang(), 'zh_CN');
assert.equal(JSON.parse(store.get('conf')).lang, 'zh_CN');
context.set_local_val('conf', 'lang', 'en');
assert.equal(context.get_local_lang(), 'en');
context.set_local_val('conf', 'dark', false);
assert.equal(context.get_local_val('conf', 'dark', true), false);
console.log('4 Chinese-default and saved-preference checks passed');
