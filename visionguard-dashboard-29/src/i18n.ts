import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import enTranslation from './locales/en/translation.json';
import esTranslation from './locales/es/translation.json';
import urTranslation from './locales/ur/translation.json';
import arTranslation from './locales/ar/translation.json';

// Configure i18next
i18n
  .use(initReactI18next)
  .init({
    resources: {
      en: {
        translation: enTranslation,
      },
      es: {
        translation: esTranslation,
      },
      ur: {
        translation: urTranslation,
      },
      ar: {
        translation: arTranslation,
      },
    },
    lng: 'en', // default language
    fallbackLng: 'en', // fallback to English if a key is missing
    interpolation: {
      escapeValue: false, // React already escapes values
    },
  });

export default i18n;
