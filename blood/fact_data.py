# blood/fact_data.py

FACT_DATABASE = [
    # ============================================================================
    # BLOOD SCIENCE & BIOLOGY (Category: 'blood')
    # ============================================================================
    {
        'category': 'blood',
        'title': 'The Human Body Replaces Blood Quickly',
        'fact_text': 'Your body replaces the plasma you donate within 24-48 hours, but red blood cells take 4-6 weeks to fully replenish.',
        'image_url': 'https://images.unsplash.com/photo-1559757148-5c350d0d3c56?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': True,
        'quiz_question': 'How long does it take for red blood cells to fully replenish after donation?',
        'correct_answer': '4-6 weeks',
        'wrong_answer_1': '24 hours',
        'wrong_answer_2': '1 week',
        'explanation': 'While plasma is replaced quickly, red blood cells take longer because bone marrow needs time to produce new cells.'
    },
    {
        'category': 'blood',
        'title': 'Blood Type Discovery Changed Medicine',
        'fact_text': 'Karl Landsteiner discovered blood groups (A, B, AB, O) in 1901, winning the Nobel Prize and making safe blood transfusions possible.',
        'image_url': 'https://images.unsplash.com/photo-1576091160399-112ba8d25d1f?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': True,
        'quiz_question': 'Who discovered blood groups and when?',
        'correct_answer': 'Karl Landsteiner in 1901',
        'wrong_answer_1': 'Louis Pasteur in 1885',
        'wrong_answer_2': 'Alexander Fleming in 1928',
        'explanation': 'Before this discovery, blood transfusions were extremely dangerous because incompatible blood types would cause fatal reactions.'
    },
    {
        'category': 'blood',
        'title': 'Your Blood is Constantly Moving',
        'fact_text': 'Your blood completes a full circulation through your body approximately once every 60 seconds. In a single day, it travels about 19,000 kilometers!',
        'image_url': 'https://images.unsplash.com/photo-1628348068343-c6a848d2b6dd?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': True,
        'quiz_question': 'How long does it take for blood to complete one full circulation?',
        'correct_answer': 'About 60 seconds',
        'wrong_answer_1': 'About 5 minutes',
        'wrong_answer_2': 'About 10 minutes',
        'explanation': 'Your heart pumps about 5 liters of blood per minute at rest, circulating all your blood very quickly.'
    },
    {
        'category': 'blood',
        'title': 'Red Blood Cells Are Incredibly Numerous',
        'fact_text': 'You have about 25 trillion red blood cells in your body. If you lined them up, they would circle the Earth 4 times!',
        'image_url': 'https://images.unsplash.com/photo-1530497610245-94d3c16cda28?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': False
    },
    {
        'category': 'blood',
        'title': 'Blood Carries Essential Nutrients',
        'fact_text': 'Blood transports oxygen, nutrients, hormones, and antibodies throughout your body while removing waste products like carbon dioxide.',
        'image_url': 'https://images.unsplash.com/photo-1559757148-5c350d0d3c56?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': False
    },
    {
        'category': 'blood',
        'title': 'The Rarest Blood Type',
        'fact_text': 'Rh-null blood, called "golden blood," is the rarest type in the world. Fewer than 50 people globally are known to have it.',
        'image_url': 'https://images.unsplash.com/photo-1576091160550-2173dba999ef?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': True,
        'quiz_question': 'What is the rarest blood type in the world?',
        'correct_answer': 'Rh-null ("golden blood")',
        'wrong_answer_1': 'AB negative',
        'wrong_answer_2': 'B negative',
        'explanation': 'Rh-null blood lacks all Rh antigens and can be donated to anyone with rare blood types, but recipients are extremely hard to find.'
    },

    # ============================================================================
    # DONATION PROCESS & IMPACT (Category: 'donation')
    # ============================================================================
    {
        'category': 'donation',
        'title': 'One Donation Can Save Three Lives',
        'fact_text': 'A single blood donation is separated into red cells, plasma, and platelets, which can help up to three different patients.',
        'image_url': 'https://images.unsplash.com/photo-1584467735871-8db9ac8afd01?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': True,
        'quiz_question': 'How many lives can one blood donation potentially save?',
        'correct_answer': 'Up to 3 lives',
        'wrong_answer_1': 'Only 1 life',
        'wrong_answer_2': 'Up to 5 lives',
        'explanation': 'Blood is separated into components: red cells for trauma patients, plasma for burn victims, and platelets for cancer patients.'
    },
    {
        'category': 'donation',
        'title': 'Blood Has a Short Shelf Life',
        'fact_text': 'Red blood cells can be stored for only 42 days, platelets for just 5 days. This is why regular donations are critical.',
        'image_url': 'https://images.unsplash.com/photo-1579684385127-1ef15d508118?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': True,
        'quiz_question': 'How long can platelets be stored?',
        'correct_answer': '5 days',
        'wrong_answer_1': '42 days',
        'wrong_answer_2': '14 days',
        'explanation': 'The short shelf life means hospitals need a constant supply of fresh blood donations to help patients in need.'
    },
    {
        'category': 'donation',
        'title': 'Every Two Seconds Someone Needs Blood',
        'fact_text': 'In Kenya and worldwide, someone needs blood every 2 seconds. Hospital demand is constant, from emergencies to routine surgeries.',
        'image_url': 'https://images.unsplash.com/photo-1516841273335-e39b37888115?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': False
    },
    {
        'category': 'donation',
        'title': 'Donation is Safe and Sterile',
        'fact_text': 'All needles and equipment are sterile and single-use. You cannot contract any disease from donating blood.',
        'image_url': 'https://images.unsplash.com/photo-1631815588090-d4bfec5b1ccb?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': False
    },
    {
        'category': 'donation',
        'title': 'Universal Donors Are Critical',
        'fact_text': 'Only 7% of people have O-negative blood (universal donor), yet it accounts for 13% of hospital requests because it can save anyone.',
        'image_url': 'https://images.unsplash.com/photo-1615461066841-6116e61058f4?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': True,
        'quiz_question': 'What percentage of people have O-negative blood?',
        'correct_answer': 'About 7%',
        'wrong_answer_1': 'About 25%',
        'wrong_answer_2': 'About 15%',
        'explanation': 'O-negative blood is in constant high demand because it can be given to any patient in emergencies when blood type is unknown.'
    },
    {
        'category': 'donation',
        'title': 'Cancer Patients Need Blood Regularly',
        'fact_text': 'A single cancer patient can need up to 8 units of blood per week during treatment. Regular donors make this possible.',
        'image_url': 'https://images.unsplash.com/photo-1579154204601-01588f351e67?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': False
    },

    # ============================================================================
    # HEALTH BENEFITS (Category: 'health')
    # ============================================================================
    {
        'category': 'health',
        'title': 'Regular Donors Live Longer',
        'fact_text': 'Studies show regular blood donors have an 88% lower risk of heart attacks and may live longer than non-donors.',
        'image_url': 'https://images.unsplash.com/photo-1579684385127-1ef15d508118?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': True,
        'quiz_question': 'How much lower is the heart attack risk for regular blood donors?',
        'correct_answer': '88% lower',
        'wrong_answer_1': '50% lower',
        'wrong_answer_2': 'No difference',
        'explanation': 'Regular blood donation helps regulate iron levels in the body, reducing oxidative stress and inflammation.'
    },
    {
        'category': 'health',
        'title': 'Free Health Screening',
        'fact_text': 'Every donation includes free tests for blood type, hemoglobin, blood pressure, and screening for infectious diseases.',
        'image_url': 'https://images.unsplash.com/photo-1584820927498-cfe5211fd8bf?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': False
    },
    {
        'category': 'health',
        'title': 'Donation Reduces Iron Overload',
        'fact_text': 'Donating blood helps reduce excess iron in your body, which can lower the risk of hemochromatosis and liver damage.',
        'image_url': 'https://images.unsplash.com/photo-1551601651-2a8555f1a136?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': False
    },
    {
        'category': 'health',
        'title': 'Burns Calories Without Exercise',
        'fact_text': 'A single blood donation burns approximately 650 calories as your body works to replenish the donated blood.',
        'image_url': 'https://images.unsplash.com/photo-1517836357463-d25dfeac3438?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': True,
        'quiz_question': 'How many calories does donating blood burn?',
        'correct_answer': 'About 650 calories',
        'wrong_answer_1': 'About 200 calories',
        'wrong_answer_2': 'About 1000 calories',
        'explanation': 'Your body uses energy to produce new blood cells and plasma to replace what was donated.'
    },
    {
        'category': 'health',
        'title': 'Stimulates New Blood Cell Production',
        'fact_text': 'After donation, your body immediately starts producing fresh, new blood cells, keeping your blood supply young and healthy.',
        'image_url': 'https://images.unsplash.com/photo-1559757148-5c350d0d3c56?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': False
    },

    # ============================================================================
    # MYTHS BUSTED (Category: 'myths')
    # ============================================================================
    {
        'category': 'myths',
        'title': 'Donation Makes You Weak - Myth!',
        'fact_text': 'You only donate about 350-450ml of blood (less than 10% of total blood volume). Most people feel completely normal within hours.',
        'image_url': 'https://images.unsplash.com/photo-1559757148-5c350d0d3c56?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': True,
        'quiz_question': 'What percentage of total blood volume is typically donated?',
        'correct_answer': 'Less than 10%',
        'wrong_answer_1': 'About 25%',
        'wrong_answer_2': 'About 15%',
        'explanation': 'The average adult has 4.5-5.5 liters of blood. A donation of 350-450ml is safe and quickly replenished.'
    },
    {
        'category': 'myths',
        'title': 'You Can\'t Get Diseases From Donating - Fact!',
        'fact_text': 'All needles are sterile, single-use, and disposed of immediately. It is impossible to contract HIV, hepatitis, or any disease from donating.',
        'image_url': 'https://images.unsplash.com/photo-1631815588090-d4bfec5b1ccb?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': True,
        'quiz_question': 'Can you contract diseases from donating blood?',
        'correct_answer': 'No, it\'s impossible with sterile needles',
        'wrong_answer_1': 'Yes, there\'s a small risk',
        'wrong_answer_2': 'Only if equipment is reused',
        'explanation': 'Every needle is brand new, used once, and immediately discarded. The donation process is completely safe.'
    },
    {
        'category': 'myths',
        'title': 'Older People Can Donate - Fact!',
        'fact_text': 'Healthy adults up to 65 years (and sometimes older with doctor approval) can donate blood. Age is not a barrier if you\'re healthy.',
        'image_url': 'https://images.unsplash.com/photo-1581594549595-35f6edc7b762?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': False
    },
    {
        'category': 'myths',
        'title': 'Vegetarians Have Weak Blood - Myth!',
        'fact_text': 'Vegetarians and vegans can absolutely donate blood. As long as your hemoglobin levels are adequate, your diet doesn\'t matter.',
        'image_url': 'https://images.unsplash.com/photo-1512621776951-a57141f2eefd?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': False
    },
    {
        'category': 'myths',
        'title': 'Donation is Painful - Myth!',
        'fact_text': 'You may feel a small pinch when the needle is inserted, but the actual donation is painless. Most donors read or use their phones during donation.',
        'image_url': 'https://images.unsplash.com/photo-1576091160550-2173dba999ef?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': False
    },
    {
        'category': 'myths',
        'title': 'You Need to Rest for Days - Myth!',
        'fact_text': 'Most donors return to normal activities immediately. Just avoid strenuous exercise for 24 hours and stay hydrated.',
        'image_url': 'https://images.unsplash.com/photo-1517836357463-d25dfeac3438?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': False
    },

    # ============================================================================
    # FUN FACTS & HISTORY (Category: 'fun')
    # ============================================================================
    {
        'category': 'fun',
        'title': 'The First Successful Blood Transfusion',
        'fact_text': 'The first successful human blood transfusion was performed in 1818 by Dr. James Blundell, who used a syringe to transfer blood from husband to wife.',
        'image_url': 'https://images.unsplash.com/photo-1576091160399-112ba8d25d1f?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': True,
        'quiz_question': 'When was the first successful human blood transfusion?',
        'correct_answer': '1818',
        'wrong_answer_1': '1901',
        'wrong_answer_2': '1750',
        'explanation': 'Dr. Blundell performed this historic transfusion to save a woman suffering from postpartum hemorrhage.'
    },
    {
        'category': 'fun',
        'title': 'Coconut Water Was Used as Blood Plasma',
        'fact_text': 'During World War II, coconut water was sometimes used as emergency plasma because it\'s sterile and has a similar electrolyte composition to blood.',
        'image_url': 'https://images.unsplash.com/photo-1589751133946-f5bd0a67c4d2?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': False
    },
    {
        'category': 'fun',
        'title': 'Blood Types Vary by Ethnicity',
        'fact_text': 'Blood type distribution varies globally. In Kenya, O+ is most common (≈45%), while in some Asian countries, B+ dominates.',
        'image_url': 'https://images.unsplash.com/photo-1451187580459-43490279c0fa?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': False
    },
    {
        'category': 'fun',
        'title': 'The Bombay Blood Group',
        'fact_text': 'The Bombay blood group (hh) is so rare that only 1 in 10,000 Indians and 1 in million Europeans have it. It was discovered in Mumbai in 1952.',
        'image_url': 'https://images.unsplash.com/photo-1524492412937-b28074a5d7da?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': False
    },
    {
        'category': 'fun',
        'title': 'World Blood Donor Day',
        'fact_text': 'June 14th is World Blood Donor Day, honoring Karl Landsteiner\'s birthday and celebrating voluntary blood donors worldwide.',
        'image_url': 'https://images.unsplash.com/photo-1559757175-0eb30cd8c063?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': True,
        'quiz_question': 'When is World Blood Donor Day celebrated?',
        'correct_answer': 'June 14th',
        'wrong_answer_1': 'December 1st',
        'wrong_answer_2': 'September 5th',
        'explanation': 'This date honors Karl Landsteiner, the scientist who discovered blood groups and made safe transfusions possible.'
    },
    {
        'category': 'fun',
        'title': 'Horseshoe Crabs Have Blue Blood',
        'fact_text': 'Horseshoe crabs have blue blood due to copper (not iron). Their blood is used to test medical equipment for contamination before use in humans!',
        'image_url': 'https://images.unsplash.com/photo-1559590558-2bf15bed8c46?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': False
    },
    {
        'category': 'fun',
        'title': 'James Harrison - The Man With Golden Arm',
        'fact_text': 'Australian James Harrison donated blood over 1,000 times in 60 years. His rare antibodies saved an estimated 2.4 million babies from Rhesus disease.',
        'image_url': 'https://images.unsplash.com/photo-1628348068343-c6a848d2b6dd?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': False
    },

    # ============================================================================
    # KENYAN CONTEXT (Category: 'local')
    # ============================================================================
    {
        'category': 'local',
        'title': 'Kenya Needs 1 Million Units Annually',
        'fact_text': 'Kenya needs approximately 1 million units of blood per year, but collects only about 150,000-200,000 units, creating a critical shortage.',
        'image_url': 'https://images.unsplash.com/photo-1488521787991-ed7bbaae773c?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': True,
        'quiz_question': 'How many blood units does Kenya need annually?',
        'correct_answer': 'About 1 million units',
        'wrong_answer_1': 'About 500,000 units',
        'wrong_answer_2': 'About 2 million units',
        'explanation': 'Kenya faces a severe blood shortage, with donations meeting only 15-20% of the national need.'
    },
    {
        'category': 'local',
        'title': 'KNBTS Coordinates Blood Services',
        'fact_text': 'The Kenya National Blood Transfusion Service (KNBTS) coordinates all blood collection, testing, and distribution across Kenya\'s 47 counties.',
        'image_url': 'https://images.unsplash.com/photo-1516841273335-e39b37888115?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': False
    },
    {
        'category': 'local',
        'title': 'Maternal Health Depends on Blood',
        'fact_text': 'In Kenya, postpartum hemorrhage is a leading cause of maternal death. Blood donations directly save mothers during childbirth complications.',
        'image_url': 'https://images.unsplash.com/photo-1584467735579-630f74c0ca2c?ixlib=rb-4.0.3&auto=format&fit=crop&w=800',
        'has_quiz': False
    },
]

# ============================================================================
# QUICK FACTS FOR SIDEBAR/TOOLTIPS
# ============================================================================
QUICK_FACTS = [
    "🩸 Type O-negative blood can be given to ANY patient (universal donor)",
    "💪 Donating blood burns about 650 calories per donation",
    "🌡️ Blood makes up about 7% of your body weight",
    "🚗 You can donate every 56 days (approximately 8 weeks)",
    "👥 Only 3% of age-eligible people donate blood regularly in Kenya",
    "🔄 Your body has about 5 liters (1.3 gallons) of blood",
    "⏱️ A whole blood donation takes only 8-10 minutes",
    "🎂 You must be at least 16-17 years old to donate (with parental consent)",
    "⚖️ You need to weigh at least 50kg (110 lbs) to donate safely",
    "💤 You should get a good night's sleep before donating",
    "🥤 Drink 500ml of water before and after donating",
    "🍽️ Eat a healthy meal 2-3 hours before your donation",
    "❤️ One donation can save up to 3 lives",
    "⏰ Blood platelets have a shelf life of only 5 days",
    "🏥 Every 2 seconds, someone in the world needs blood",
    "🔬 All donated blood is tested for infections before use",
    "💉 New, sterile needles are used for every donation",
    "🌍 Kenya needs 1 million blood units annually but collects only 150,000",
    "📅 June 14th is World Blood Donor Day",
    "🎯 Regular donors have 88% lower risk of heart attacks",
]

# ============================================================================
# DONATION TIPS
# ============================================================================
DONATION_TIPS = [
    {
        'title': 'Before Donation',
        'tips': [
            'Get 7-8 hours of sleep the night before',
            'Eat a healthy, iron-rich meal 2-3 hours before',
            'Drink at least 500ml of water',
            'Avoid fatty foods on donation day',
            'Bring your ID and donor card (if you have one)',
        ]
    },
    {
        'title': 'During Donation',
        'tips': [
            'Relax and breathe normally',
            'Squeeze a stress ball or make a fist periodically',
            'Tell staff if you feel dizzy or uncomfortable',
            'Stay calm - the process is quick and safe',
        ]
    },
    {
        'title': 'After Donation',
        'tips': [
            'Rest for 10-15 minutes and have refreshments',
            'Drink extra fluids for 24 hours',
            'Avoid strenuous exercise for 24 hours',
            'Keep the bandage on for 4-6 hours',
            'If you feel faint, sit or lie down immediately',
        ]
    },
]

# ============================================================================
# ELIGIBILITY CRITERIA (Kenyan Context)
# ============================================================================
ELIGIBILITY_CRITERIA = {
    'can_donate': [
        'Age 16-65 years (16-17 need parental consent)',
        'Weight at least 50kg (110 lbs)',
        'Hemoglobin level ≥12.5 g/dL',
        'Good general health',
        'No active infections or fever',
        'At least 8 weeks since last donation',
    ],
    'cannot_donate': [
        'Pregnant or breastfeeding (wait 6 months after childbirth)',
        'Recent tattoo or piercing (wait 6 months)',
        'Traveled to malaria-endemic area (wait 3 months)',
        'Recent surgery (wait 6-12 months depending on procedure)',
        'History of hepatitis, HIV, or sexually transmitted infections',
        'Currently taking antibiotics or blood thinners',
        'Recent vaccination (waiting period varies)',
    ],
    'temporary_deferral': [
        'Cold or flu (wait until fully recovered)',
        'Dental procedures (wait 24 hours)',
        'Minor injury (wait until healed)',
        'Medication (consult with medical staff)',
    ]
}
