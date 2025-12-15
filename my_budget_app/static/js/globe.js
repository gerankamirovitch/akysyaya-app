// 3D Финансовый глобус
class FinancialGlobe {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        if (!this.container) return;
        
        this.init();
        this.addExpenseMarkers();
        this.animate();
    }
    
    init() {
        // Сцена
        this.scene = new THREE.Scene();
        
        // Камера
        this.camera = new THREE.PerspectiveCamera(75, 1, 0.1, 1000);
        this.camera.position.z = 5;
        
        // Рендерер
        this.renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
        this.renderer.setSize(300, 300);
        this.container.appendChild(this.renderer.domElement);
        
        // Освещение
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
        this.scene.add(ambientLight);
        
        const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
        directionalLight.position.set(5, 3, 5);
        this.scene.add(directionalLight);
        
        // Земля (глобус)
        const geometry = new THREE.SphereGeometry(2, 32, 32);
        const texture = this.createEarthTexture();
        const material = new THREE.MeshPhongMaterial({ 
            map: texture,
            specular: 0x222222,
            shininess: 5
        });
        
        this.earth = new THREE.Mesh(geometry, material);
        this.scene.add(this.earth);
        
        // Облака
        const cloudGeometry = new THREE.SphereGeometry(2.05, 32, 32);
        const cloudMaterial = new THREE.MeshPhongMaterial({
            map: this.createCloudTexture(),
            transparent: true,
            opacity: 0.3
        });
        
        this.clouds = new THREE.Mesh(cloudGeometry, cloudMaterial);
        this.scene.add(this.clouds);
        
        // Орбитальные контролы
        this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableZoom = false;
        this.controls.enablePan = false;
        this.controls.autoRotate = true;
        this.controls.autoRotateSpeed = 0.5;
        
        // Маркеры расходов
        this.markers = new THREE.Group();
        this.scene.add(this.markers);
    }
    
    createEarthTexture() {
        const canvas = document.createElement('canvas');
        canvas.width = 512;
        canvas.height = 256;
        const ctx = canvas.getContext('2d');
        
        // Градиент для океанов
        const gradient = ctx.createLinearGradient(0, 0, 512, 256);
        gradient.addColorStop(0, '#1a2980');
        gradient.addColorStop(1, '#26d0ce');
        
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, 512, 256);
        
        // Континенты
        ctx.fillStyle = '#2d5016';
        ctx.fillRect(100, 50, 150, 80); // Пример континента
        
        ctx.fillStyle = '#8B4513';
        ctx.fillRect(300, 120, 120, 60); // Другой континент
        
        const texture = new THREE.CanvasTexture(canvas);
        return texture;
    }
    
    createCloudTexture() {
        const canvas = document.createElement('canvas');
        canvas.width = 512;
        canvas.height = 256;
        const ctx = canvas.getContext('2d');
        
        ctx.fillStyle = 'rgba(255, 255, 255, 0.1)';
        
        // Случайные облака
        for (let i = 0; i < 20; i++) {
            const x = Math.random() * 512;
            const y = Math.random() * 256;
            const size = Math.random() * 30 + 10;
            
            ctx.beginPath();
            ctx.arc(x, y, size, 0, Math.PI * 2);
            ctx.fill();
        }
        
        return new THREE.CanvasTexture(canvas);
    }
    
    addExpenseMarkers() {
        // Пример данных о расходах по странам
        const expenses = [
            { country: 'США', lat: 40, lon: -100, amount: 1500, color: 0xff0000 },
            { country: 'Россия', lat: 60, lon: 100, amount: 800, color: 0x0000ff },
            { country: 'Китай', lat: 35, lon: 105, amount: 1200, color: 0x00ff00 },
            { country: 'Германия', lat: 51, lon: 10, amount: 900, color: 0xffff00 },
            { country: 'Япония', lat: 36, lon: 138, amount: 1100, color: 0xff00ff }
        ];
        
        expenses.forEach(expense => {
            const marker = this.createExpenseMarker(expense);
            this.markers.add(marker);
        });
    }
    
    createExpenseMarker(expense) {
        // Конвертируем широту/долготу в 3D координаты
        const phi = (90 - expense.lat) * (Math.PI / 180);
        const theta = (expense.lon + 180) * (Math.PI / 180);
        
        const radius = 2.1;
        const x = -radius * Math.sin(phi) * Math.cos(theta);
        const y = radius * Math.cos(phi);
        const z = radius * Math.sin(phi) * Math.sin(theta);
        
        // Создаём маркер
        const size = Math.min(expense.amount / 500, 0.3);
        const geometry = new THREE.SphereGeometry(size, 16, 16);
        const material = new THREE.MeshBasicMaterial({ 
            color: expense.color,
            transparent: true,
            opacity: 0.8
        });
        
        const marker = new THREE.Mesh(geometry, material);
        marker.position.set(x, y, z);
        
        // Добавляем свечение
        const glowGeometry = new THREE.SphereGeometry(size * 1.5, 16, 16);
        const glowMaterial = new THREE.MeshBasicMaterial({
            color: expense.color,
            transparent: true,
            opacity: 0.3
        });
        
        const glow = new THREE.Mesh(glowGeometry, glowMaterial);
        marker.add(glow);
        
        // Анимация пульсации
        marker.userData = {
            originalScale: size,
            pulseSpeed: Math.random() * 0.02 + 0.01
        };
        
        return marker;
    }
    
    animate() {
        requestAnimationFrame(() => this.animate());
        
        // Вращение земли
        this.earth.rotation.y += 0.001;
        
        // Вращение облаков
        this.clouds.rotation.y += 0.0005;
        
        // Пульсация маркеров
        this.markers.children.forEach(marker => {
            const scale = marker.userData.originalScale * 
                         (1 + Math.sin(Date.now() * marker.userData.pulseSpeed) * 0.2);
            marker.scale.setScalar(scale);
        });
        
        this.controls.update();
        this.renderer.render(this.scene, this.camera);
    }
}

// Инициализация глобуса при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    const globe = new FinancialGlobe('globe-container');
    window.financialGlobe = globe;
});